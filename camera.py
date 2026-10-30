"""Camera isolation: blocked drivers can be terminated without blocking safety/UI."""
import multiprocessing as mp
import queue
import time

def capture_worker(source, backend, frames):
    import cv2
    cap = None
    try:
        if source.isdigit():
            api = {'DSHOW':cv2.CAP_DSHOW, 'MSMF':cv2.CAP_MSMF, 'AUTO':cv2.CAP_ANY}[backend]
            cap = cv2.VideoCapture(int(source), api)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
        else:
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG,
                                   [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000])
        if not cap.isOpened():
            raise RuntimeError('Cannot open source. Check DroidCam connection, camera index and backend.')
        while True:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError('Video stopped. Reconnect DroidCam and restart the preview.')
            if frame.shape[1] > 960:
                frame = cv2.resize(frame, (960, round(frame.shape[0]*960/frame.shape[1])))
            item = (time.monotonic(), frame, '')
            try:
                frames.put_nowait(item)
            except queue.Full:
                try:
                    frames.get_nowait()
                except queue.Empty:
                    pass
                try:
                    frames.put_nowait(item)
                except queue.Full:
                    pass
    except Exception as exc:
        try:
            frames.put((time.monotonic(), None, str(exc)), timeout=.5)
        except queue.Full:
            pass
    finally:
        if cap is not None:
            cap.release()

class Camera:
    def __init__(self, source, backend):
        self.frames = mp.Queue(maxsize=2)
        self.process = mp.Process(target=capture_worker, args=(str(source), backend, self.frames), daemon=True)
        self.process.start()

    def latest(self):
        item = None
        while True:
            try:
                item = self.frames.get_nowait()
            except queue.Empty:
                return item

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=2)
        self.frames.close()

def probe(source, backend, timeout=7):
    camera = Camera(source, backend)
    try:
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            item = camera.latest()
            if item:
                _, frame, error = item
                return error or f'OK: {frame.shape[1]} x {frame.shape[0]}'
            if not camera.process.is_alive():
                return 'Source unavailable'
            time.sleep(.05)
        return 'Timed out opening source'
    finally:
        camera.close()
