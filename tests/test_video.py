"""Real OpenCV capture against a generated loopback MJPEG stream; no camera."""
import http.server
import threading
import time
import pytest
from camera import Camera, probe
from config import validate

@pytest.fixture
def stream():
    import cv2
    import numpy as np
    ok, jpg = cv2.imencode('.jpg', np.zeros((240,320,3), dtype=np.uint8))
    assert ok
    data = jpg.tobytes()
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                for _ in range(300):
                    self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data+b'\r\n')
                    self.wfile.flush()
                    time.sleep(.03)
            except (ConnectionError, OSError): pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/video'
    server.shutdown(); server.server_close(); thread.join(timeout=2)

def test_real_mjpeg_capture_and_shutdown(stream):
    assert probe(stream,'AUTO').startswith('OK: 320 x 240')
    camera=Camera(stream,'AUTO')
    try:
        until=time.monotonic()+7
        item=None
        while time.monotonic()<until:
            item=camera.latest()
            if item: break
            time.sleep(.02)
        assert item and item[1].shape==(240,320,3)
    finally:
        camera.close()
    assert not camera.process.is_alive()

def test_missing_stream_returns_without_hanging():
    started=time.monotonic()
    result=probe('http://127.0.0.1:1/video','AUTO',timeout=2)
    assert not result.startswith('OK:')
    assert time.monotonic()-started<5

def test_full_preview_with_local_video_and_no_input(stream,monkeypatch):
    import cv2
    import runtime
    from selftest import FakeMouse
    sink=FakeMouse()
    monkeypatch.setattr(runtime,'Mouse',lambda:sink)
    start=time.monotonic()
    shown=[]
    real_show=cv2.imshow
    def show(title,frame):
        shown.append(frame.shape)
        real_show(title,frame)
    monkeypatch.setattr(cv2,'imshow',show)
    real_wait=cv2.waitKey
    def wait(ms):
        real_wait(ms)
        # Cold MediaPipe import/model initialization is not part of the capture timeout.
        return ord('q') if shown.count((240,320,3)) >= 5 or time.monotonic()-start>15 else -1
    monkeypatch.setattr(cv2,'waitKey',wait)
    runtime.run(validate({'source':stream}))
    assert (240,320,3) in shown
    assert not sink.events
