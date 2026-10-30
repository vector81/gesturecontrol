"""Validated, local-only configuration."""
import json
import math
from pathlib import Path
from urllib.parse import urlparse
import ipaddress

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'
DEFAULTS = dict(source='0', backend='DSHOW', mirror=True, rotation=0,
                sensitivity=1.4, smoothing=0.07, deadzone=2.0,
                dwell=0.18, click_cooldown=0.65, pinch_on=0.28, pinch_off=0.42,
                scroll_speed=28.0, max_speed=2200.0, confidence=0.7,
                cursor_only=True, relaxed_pose=False, absolute_cursor=False,
                auto_resume=False, roi=[0.15, 0.15, 0.85, 0.85])

def validate(raw):
    c = DEFAULTS | raw
    c['source'] = str(c['source']).strip()
    if c['source'].isdigit():
        if not 0 <= int(c['source']) <= 99:
            raise ValueError('Camera index must be 0–99.')
    else:
        u = urlparse(c['source'])
        try:
            address = ipaddress.ip_address(u.hostname or '')
            local = address.is_private or address.is_loopback or address.is_link_local
        except ValueError:
            local = False
        if u.scheme not in ('http', 'https', 'rtsp') or not local or u.username or u.password:
            raise ValueError('Use a camera index or a local IP stream URL, e.g. http://192.168.1.20:4747/video')
    if c['backend'] not in ('DSHOW', 'MSMF', 'AUTO'):
        raise ValueError('Backend must be DSHOW, MSMF or AUTO.')
    if c['rotation'] not in (0, 90, 180, 270):
        raise ValueError('Rotation must be 0, 90, 180 or 270.')
    for key, low, high in [('sensitivity', .2, 5), ('smoothing', 0, .5),
                           ('deadzone', 0, 20), ('dwell', .1, 1),
                           ('click_cooldown', .25, 3), ('pinch_on', .1, .5),
                           ('pinch_off', .2, .8), ('scroll_speed', 1, 100),
                           ('max_speed', 100, 5000), ('confidence', .5, .95)]:
        c[key] = float(c[key])
        if not math.isfinite(c[key]) or not low <= c[key] <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
    if c['pinch_off'] <= c['pinch_on']:
        raise ValueError('pinch_off must exceed pinch_on (release hysteresis).')
    r = c['roi']
    if len(r) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in r):
        raise ValueError('ROI must have four finite numbers.')
    if not (0 <= r[0] < r[2] <= 1 and 0 <= r[1] < r[3] <= 1 and r[2]-r[0] >= .15 and r[3]-r[1] >= .15):
        raise ValueError('Calibration region must span at least 15% of width and height.')
    for key in ('mirror', 'cursor_only', 'relaxed_pose', 'absolute_cursor', 'auto_resume'):
        if not isinstance(c[key], bool):
            raise ValueError(f'{key} must be true or false.')
    return c

def load():
    return validate(json.loads(CONFIG.read_text()) if CONFIG.exists() else {})

def save(config):
    c = validate(config)
    temp = CONFIG.with_suffix('.tmp')
    temp.write_text(json.dumps(c, indent=2) + '\n')
    temp.replace(CONFIG)
