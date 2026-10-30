"""Local MediaPipe preview and guarded Windows input."""
import ctypes
import json
import threading
import time

from config import ROOT, save, validate
from engine import Controller, classify
from camera import Camera
from tracking import HandSelector

def arm_blocker(now, last_video, gesture, point, roi):
    if now-last_video >= .3:
        return 'Waiting for live video'
    if gesture == 'MULTIPLE':
        return 'Keep only ONE hand visible to the camera'
    if gesture == 'LOST':
        return 'Show your full hand and wrist to the camera'
    if gesture != 'POINT':
        return 'Extend INDEX only; fold middle/ring/little fingers'
    if not (roi[0] <= point[0] <= roi[2] and roi[1] <= point[1] <= roi[3]):
        return 'Move index fingertip INSIDE blue rectangle'
    return ''

class ArmRequest:
    """A deliberate keypress grants five seconds to present a stable pose."""
    def __init__(self):
        self.cancel()

    def cancel(self):
        self.deadline = 0
        self.ready_since = None

    def request(self, now):
        self.deadline = now + 5
        self.ready_since = None

    def update(self, now, ready, emergency=False):
        if emergency or (self.deadline and now >= self.deadline):
            self.cancel()
            return 'cancelled'
        if not self.deadline:
            return 'idle'
        if not ready:
            self.ready_since = None
        elif self.ready_since is None:
            self.ready_since = now
        elif now-self.ready_since >= .35:
            self.cancel()
            return 'arm'
        return 'waiting'

class Mouse:
    def __init__(self):
        import pyautogui
        self.p = pyautogui
        self.p.PAUSE = 0
        self.p.FAILSAFE = True

    def position(self): return self.p.position()
    def size(self): return self.p.size()
    def move(self, x, y): self.p.moveTo(x, y)
    def click(self): self.p.click()
    def down(self): self.p.mouseDown()
    def scroll(self, count): self.p.scroll(count)
    def up(self):
        # Release must work even if the PyAutoGUI corner failsafe is active.
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

def safety_loop(controller, stop, emergency_event):
    while not stop.wait(.02):
        if ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000:  # F8, global
            emergency_event.set()
            controller.disable('EMERGENCY F8')
        controller.watchdog(time.monotonic())

def run(config, video_only=False, dry_run=False, bridge=None):
    import cv2
    import numpy as np
    import mediapipe as mp
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except AttributeError:
        pass
    mouse = Mouse()
    if dry_run:
        from selftest import FakeMouse
        mouse = FakeMouse()
    controller = Controller(config, mouse)
    if video_only:
        controller.disable('VIDEO TEST')
    if bridge is not None:
        bridge.controller = controller
        controller.disable('PREVIEW ONLY')
    stop = threading.Event()
    emergency_event = threading.Event()
    safety = threading.Thread(target=safety_loop, args=(controller, stop, emergency_event), daemon=True)
    safety.start()
    camera = None
    detector = None
    title = 'GestureControl - LOCAL PREVIEW'
    calibration = []
    calibrating = False
    arm_request = ArmRequest()
    hand_selector = HandSelector()
    selected_hand = None
    count = 0
    frame_shape = [480, 640]

    def click(event, x, y, flags, param):
        nonlocal calibrating
        if calibrating and event == cv2.EVENT_LBUTTONDOWN:
            calibration.append((x/frame_shape[1], y/frame_shape[0]))
            if len(calibration) == 2:
                a, b = calibration
                region = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
                if region[2]-region[0] >= .15 and region[3]-region[1] >= .15:
                    config['roi'] = region
                    save(config)
                    controller.disable('CALIBRATION SAVED')
                    calibrating = False
                else:
                    calibration.clear()
                    controller.status = 'Region too small. Click two corners again.'

    try:
        if not video_only:
            model = ROOT / 'models' / 'hand_landmarker.task'
            if not model.exists():
                raise RuntimeError('Missing hand model. Run Setup.bat first.')
            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
                min_hand_detection_confidence=config['confidence'],
                min_hand_presence_confidence=config['confidence'],
                min_tracking_confidence=config['confidence'])
            detector = mp.tasks.vision.HandLandmarker.create_from_options(options)
        camera = Camera(config['source'], config['backend'])
        if bridge is not None:
            bridge.camera = camera
        else:
            cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
            cv2.setMouseCallback(title, click)
        started = last_video = time.monotonic()
        last_stamp = 0
        last_gesture = ''
        point = (0, 0)
        f9_was_down = False
        last_diagnostic = 0
        fps = 0.0
        display = np.zeros((480, 640, 3), dtype=np.uint8)
        error = ''
        landmark_payload = []
        while True:
            quit_requested = False
            if bridge is not None:
                for action, value in bridge.drain():
                    if action in ('pause','quit'):
                        arm_request.cancel()
                        controller.disable('PAUSED FROM DASHBOARD')
                        quit_requested |= action == 'quit'
                    elif action == 'resume' and not video_only:
                        if not (ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000) and not emergency_event.is_set():
                            if config['auto_resume']:
                                controller.want_control = True
                                controller.status = 'WAITING FOR SELECTED HAND'
                            else:
                                arm_request.request(time.monotonic())
                    elif action == 'switch':
                        arm_request.cancel()
                        controller.suspend('HAND CHANGED')
                        hand_selector.switch()
                    elif action == 'settings':
                        try:
                            updated = validate(config | value)
                            with controller.lock:
                                controller.suspend('SETTINGS UPDATED')
                                config.update(updated)
                                save(config)
                        except (ValueError, OSError) as exc:
                            controller.disable(str(exc))
            if quit_requested:
                break
            item = camera.latest()
            now = time.monotonic()
            fresh = False
            if item:
                captured, frame, error = item
                if frame is not None and now-captured < .3:
                    fresh = True
                    fps = .9*fps+.1/max(.001, now-last_video)
                    last_video = now
                    if controller.status.startswith('VIDEO UNAVAILABLE'):
                        controller.status = ('VIDEO CONNECTED - automatic hand tracking' if controller.want_control
                                             else 'VIDEO CONNECTED - F9 to enable')
                    if config['rotation']:
                        frame = cv2.rotate(frame, {90:cv2.ROTATE_90_CLOCKWISE, 180:cv2.ROTATE_180, 270:cv2.ROTATE_90_COUNTERCLOCKWISE}[config['rotation']])
                    if config['mirror']:
                        frame = cv2.flip(frame, 1)
                    frame_shape[:] = frame.shape[:2]
                    display = frame
                    if detector:
                        stamp = max(last_stamp+1, int(captured*1000))
                        last_stamp = stamp
                        result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                                                                    data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), stamp)
                        count = len(result.hand_landmarks)
                        selected_hand = hand_selector.select(result.hand_landmarks, result.handedness, config['roi'])
                        landmark_payload = [dict(selected=i==selected_hand, points=[(p.x,p.y) for p in hand])
                                            for i,hand in enumerate(result.hand_landmarks)]
                        gesture, point = 'LOST', (0, 0)
                        if selected_hand is not None:
                            gesture, point, ratio = classify(result.hand_landmarks[selected_hand], frame.shape[1]/frame.shape[0], config, last_gesture == 'PINCH')
                        last_gesture = gesture
                        # Late inference cannot actuate input using an old image.
                        if time.monotonic()-captured > .4:
                            controller.suspend('FRAME TOO OLD')
                        else:
                            controller.update(gesture, point, time.monotonic())
                        connections = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
                                       (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),
                                       (15,16),(13,17),(0,17),(17,18),(18,19),(19,20)]
                        for hand_index, hand in enumerate(result.hand_landmarks):
                            colour = (90,220,80) if hand_index == selected_hand else (100,100,100)
                            pts = [(int(p.x*frame.shape[1]), int(p.y*frame.shape[0])) for p in hand]
                            for a,b in connections:
                                cv2.line(display, pts[a], pts[b], colour, 2)
                            for p in pts:
                                cv2.circle(display, p, 4, (0,200,255) if hand_index == selected_hand else colour, -1)
            if error or now-last_video > .5:
                controller.suspend('VIDEO UNAVAILABLE')
            if not camera.process.is_alive() and not error:
                error = 'Camera worker stopped. Close preview and check connection.'
            if now-started > 10 and now-last_video > 10:
                error = 'No video after 10 seconds. Check source, backend and DroidCam.'
            blocker = arm_blocker(time.monotonic(), last_video, last_gesture, point, config['roi'])
            f8_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000) or emergency_event.is_set()
            emergency_event.clear()
            pending_before = bool(arm_request.deadline)
            arm_result = arm_request.update(time.monotonic(), not blocker, emergency=f8_down)
            if arm_result == 'arm':
                controller.arm(time.monotonic())
            elif arm_result == 'cancelled' and pending_before:
                controller.disable('EMERGENCY F8' if f8_down else 'ARM REQUEST EXPIRED')
            elif arm_request.deadline:
                remaining = max(0, arm_request.deadline-time.monotonic())
                controller.status = f'ARMING {remaining:.1f}s - show selected hand in blue rectangle'
            canvas = display.copy()
            h,w = canvas.shape[:2]
            r = config['roi']
            cv2.rectangle(canvas, (int(r[0]*w),int(r[1]*h)), (int(r[2]*w),int(r[3]*h)), (255,160,50), 1)
            if bridge is not None and fresh:
                bridge.publish(frame=canvas.copy(), geometry=landmark_payload)
            status = 'VIDEO TEST - mouse disabled' if video_only else controller.status
            if dry_run:
                status = 'DRY RUN: ' + status
            blocker = arm_blocker(time.monotonic(), last_video, last_gesture, point, config['roi'])
            hint = ('Control ON' if controller.enabled else blocker or ('AUTO RESUME' if controller.want_control else 'READY - press F9 to control cursor'))
            lines = [status, f'{fps:.1f} FPS | {last_gesture or "none"} | {hint}',
                     'F9: GLOBAL arm/pause | F8: GLOBAL STOP | Q/Esc: quit',
                     f'H: switch hand ({hand_selector.label or "Auto"}) | C: calibrate | M: cursor-only']
            if calibrating:
                lines[0] = f'CALIBRATE: click {"top-left" if not calibration else "bottom-right"} of reachable hand area'
            if error:
                lines[1] = error
            for i,line in enumerate(lines):
                cv2.rectangle(canvas, (0,i*25), (w,i*25+25), (20,20,20), -1)
                cv2.putText(canvas, line, (8,18+i*25), cv2.FONT_HERSHEY_SIMPLEX, .45, (100,240,180), 1, cv2.LINE_AA)
            if bridge is None:
                cv2.imshow(title, canvas)
            if now-last_diagnostic >= .25:
                diagnostic = dict(enabled=controller.enabled, status=controller.status,
                                  gesture=last_gesture, point=point, arm_blocker=blocker,
                                  fps=round(fps,1), frame_age=round(time.monotonic()-last_video,3),
                                  dry_run=dry_run, cursor_only=config['cursor_only'],
                                  arm_pending=bool(arm_request.deadline), auto_resume=controller.want_control,
                                  absolute_cursor=config['absolute_cursor'], relaxed_pose=config['relaxed_pose'],
                                  selected_hand=hand_selector.label, visible_hands=count,
                                  controlling_hand_visible=selected_hand is not None,
                                  error=error, config=config.copy(),
                                  width=w, height=h)
                if bridge is not None:
                    bridge.publish(state=diagnostic)
                try:
                    (ROOT/'live_status.json').write_text(json.dumps(diagnostic,indent=2))
                except OSError:
                    pass
                last_diagnostic = now
            key = (cv2.waitKey(1) & 0xFF) if bridge is None else 255
            f9_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x78) & 0x8000)
            arm_requested = key == 32 or (f9_down and not f9_was_down)
            f9_was_down = f9_down
            if key in (27, ord('q')) or (bridge is None and cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1):
                break
            if arm_requested and not video_only and not calibrating:
                if controller.enabled or controller.want_control:
                    controller.disable()
                    arm_request.cancel()
                elif arm_request.deadline:
                    arm_request.cancel()
                    controller.disable('ARM REQUEST CANCELLED')
                elif not f8_down:
                    arm_request.request(time.monotonic())
                else:
                    controller.status = 'Release F8 before arming'
            elif key == ord('h'):
                arm_request.cancel()
                controller.suspend('HAND CHANGED')
                hand_selector.switch()
            elif key == ord('c'):
                arm_request.cancel()
                controller.disable('CALIBRATING')
                calibrating = not calibrating
                calibration.clear()
            elif key == ord('m'):
                arm_request.cancel()
                controller.disable('MODE CHANGED')
                config['cursor_only'] = not config['cursor_only']
                save(config)
            elif key in (ord('+'), ord('='), ord('-')):
                arm_request.cancel()
                controller.disable('SENSITIVITY CHANGED')
                config['sensitivity'] = round(max(.2, min(5, config['sensitivity']+(-.1 if key == ord('-') else .1))), 2)
                save(config)
            if not fresh:
                time.sleep(.005)
    finally:
        controller.disable('CLOSED')
        stop.set()
        safety.join(timeout=1)
        if camera:
            camera.close()
        if detector:
            detector.close()
        if bridge is None:
            cv2.destroyAllWindows()
        else:
            bridge.finished.set()
