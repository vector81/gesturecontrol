"""Pure gesture state machine; all input effects are injected for testing."""
import math
import threading

def distance(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def classify(points, aspect, cfg, pinched=False):
    if cfg.get('relaxed_pose') and cfg['cursor_only']:
        # Cursor-only mode has no gesture actions to confuse with a relaxed hand.
        return 'POINT', (points[8].x, points[8].y), 1.0
    # Scale x to image aspect so pinch ratios do not depend on stream shape.
    p = [(q.x * aspect, q.y) for q in points]
    scale = max(distance(p[5], p[17]), distance(p[0], p[9]), .025)
    extended = []
    for base in (5, 9, 13, 17):
        a, b, tip = p[base], p[base+1], p[base+3]
        u, v = (a[0]-b[0], a[1]-b[1]), (tip[0]-b[0], tip[1]-b[1])
        cosine = (u[0]*v[0]+u[1]*v[1]) / max(math.hypot(*u)*math.hypot(*v), 1e-8)
        extended.append(cosine < -.65 and distance(tip, p[0]) > distance(b, p[0])*1.12)
    ratio = distance(p[4], p[8])/scale
    threshold = cfg['pinch_off'] if pinched else cfg['pinch_on']
    if all(extended):
        gesture = 'PALM'
    elif ratio < threshold and not extended[1] and not extended[2] and not extended[3]:
        gesture = 'PINCH'
    elif not any(extended):
        gesture = 'FIST'
    elif extended == [True, True, False, False]:
        gesture = 'SCROLL'
    elif extended == [True, False, False, False]:
        gesture = 'POINT'
    else:
        gesture = 'UNKNOWN'
    center = ((points[0].x+points[9].x)/2, (points[0].y+points[9].y)/2)
    point = (points[8].x, points[8].y)
    scroll = ((points[8].x+points[12].x)/2, (points[8].y+points[12].y)/2)
    return gesture, center if gesture == 'FIST' else scroll if gesture == 'SCROLL' else point, ratio

class Controller:
    def __init__(self, config, output):
        self.c, self.out = config, output
        self.lock = threading.RLock()
        self.enabled = False
        self.want_control = config.get('auto_resume', False)
        self.resume_since = None
        self.dragging = False
        self.status = 'PAUSED - Space to arm'
        self.last_frame = 0.0
        self.last_click = -100.0
        self.reset()

    def reset(self):
        self.candidate = None
        self.since = 0.0
        self.mode = None
        self.anchor = None
        self.filtered = None
        self.target = None
        self.last_time = None
        self.click_ready = False
        self.scroll_remainder = 0.0

    def release(self):
        if self.dragging:
            self.out.up()
            self.dragging = False

    def disable(self, reason='PAUSED'):
        with self.lock:
            self.want_control = False
            self.resume_since = None
            self.enabled = False
            self.release()
            self.reset()
            self.status = reason + ' - F9 to enable'

    def suspend(self, reason):
        with self.lock:
            resume = self.want_control and self.c.get('auto_resume', False)
            self.disable(reason)
            self.want_control = resume
            if resume:
                self.status = reason + ' - resumes when hand returns'

    def arm(self, now):
        with self.lock:
            self.release()
            self.reset()
            self.enabled = True
            self.want_control = True
            self.resume_since = None
            self.last_frame = now
            self.status = 'ARMED - hold index pointing'

    def watchdog(self, now):
        with self.lock:
            if self.enabled and now-self.last_frame > .5:
                self.suspend('VIDEO/TRACKING TIMEOUT')

    def update(self, gesture, point, now):
        with self.lock:
            self.last_frame = now
            r = self.c['roi']
            inside = r[0] <= point[0] <= r[2] and r[1] <= point[1] <= r[3]
            if not self.enabled:
                if self.want_control and self.c.get('auto_resume') and gesture == 'POINT' and inside:
                    if self.resume_since is None:
                        self.resume_since = now
                    if now-self.resume_since >= .25:
                        self.arm(now)
                    else:
                        self.status = 'ACQUIRING HAND - automatic resume'
                else:
                    self.resume_since = None
                    if self.want_control:
                        self.status = ('AUTO WAIT - move fingertip inside blue rectangle' if gesture == 'POINT'
                                       else 'AUTO WAIT - show one hand')
                if not self.enabled:
                    return
            if gesture in ('PALM', 'LOST', 'MULTIPLE'):
                self.suspend({'PALM':'OPEN PALM PAUSE', 'LOST':'HAND LOST', 'MULTIPLE':'USE ONE HAND'}[gesture])
                return
            r = self.c['roi']
            if gesture != 'UNKNOWN' and not (r[0] <= point[0] <= r[2] and r[1] <= point[1] <= r[3]):
                self.suspend('OUTSIDE CALIBRATION AREA')
                return
            if gesture != 'FIST':
                self.release()  # release immediately, even during transition dwell
            if gesture != self.candidate:
                self.candidate, self.since = gesture, now
                self.anchor = self.filtered = self.target = None
                self.mode = None
                self.scroll_remainder = 0.0
                if gesture not in ('POINT', 'PINCH'):
                    self.click_ready = False
            dwell = max(self.c['dwell'], .35) if gesture == 'FIST' else self.c['dwell']
            if now-self.since < dwell:
                self.status = f'SETTLING: {gesture}'
                return
            self.status = gesture + (' (cursor only)' if self.c['cursor_only'] else '')
            entering = self.mode != gesture
            self.mode = gesture
            if gesture == 'POINT':
                self.click_ready = True
                self.move(point, now)
            elif gesture == 'PINCH':
                if entering and self.click_ready and now-self.last_click >= self.c['click_cooldown']:
                    if not self.c['cursor_only']:
                        self.out.click()
                    self.last_click = now
                self.click_ready = False
            elif gesture == 'FIST' and not self.c['cursor_only']:
                if entering:
                    self.out.down()
                    self.dragging = True
                self.move(point, now)
            elif gesture == 'SCROLL' and not self.c['cursor_only']:
                if self.anchor is not None:
                    dy = self.anchor[1]-point[1]
                    if abs(dy) < .12:
                        self.scroll_remainder += dy*self.c['scroll_speed']
                        steps = max(-3, min(3, int(self.scroll_remainder)))
                        if steps:
                            self.out.scroll(steps)
                            self.scroll_remainder -= steps
                self.anchor = point

    def move(self, point, now):
        r = self.c['roi']
        if self.c.get('absolute_cursor'):
            w, h = self.out.size()
            # A fixed position mapping, independent of previous hand/cursor locations.
            tx = min(w-3, max(2, (point[0]-r[0])/(r[2]-r[0])*(w-1)))
            ty = min(h-3, max(2, (point[1]-r[1])/(r[3]-r[1])*(h-1)))
            dt = max(.001, min(.1, now-self.last_time)) if self.last_time is not None else 1/30
            self.last_time = now
            if self.filtered is None or self.c['smoothing'] == 0:
                self.filtered = (tx, ty)
            else:
                alpha = 1-math.exp(-dt/self.c['smoothing'])
                fx, fy = self.filtered
                self.filtered = (fx+(tx-fx)*alpha, fy+(ty-fy)*alpha)
            self.target = (tx, ty)
            self.out.move(round(self.filtered[0]), round(self.filtered[1]))
            return
        if not (r[0] <= point[0] <= r[2] and r[1] <= point[1] <= r[3]):
            self.anchor = self.filtered = self.target = None
            self.status = 'OUTSIDE CALIBRATION AREA'
            return
        if self.anchor is None:
            self.anchor = point
            self.target = self.filtered = tuple(self.out.position())
            self.last_time = now
            return
        dx, dy = point[0]-self.anchor[0], point[1]-self.anchor[1]
        self.anchor = point
        dt = max(.001, min(.1, now-self.last_time))
        self.last_time = now
        if math.hypot(dx, dy) > .15:
            self.suspend('HAND JUMP - REPOSITION')
            return
        w, h = self.out.size()
        gain = self.c['sensitivity']
        tx = min(w-3, max(2, self.target[0]+dx*w*gain/(r[2]-r[0])))
        ty = min(h-3, max(2, self.target[1]+dy*h*gain/(r[3]-r[1])))
        self.target = tx, ty
        alpha = 1 if self.c['smoothing'] == 0 else 1-math.exp(-dt/self.c['smoothing'])
        fx, fy = self.filtered
        sx, sy = (tx-fx)*alpha, (ty-fy)*alpha
        length = math.hypot(sx, sy)
        if length < self.c['deadzone']:
            return
        limit = self.c['max_speed']*dt
        if length > limit:
            sx, sy = sx*limit/length, sy*limit/length
        self.filtered = fx+sx, fy+sy
        self.out.move(round(fx+sx), round(fy+sy))
