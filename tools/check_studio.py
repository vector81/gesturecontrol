"""Live UI acceptance check with real video and a fake mouse sink."""
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from selftest import FakeMouse
    import runtime
    from desktop import Studio
    sink=FakeMouse(); runtime.Mouse=lambda:sink
    app=QApplication([]); window=Studio(autoconnect=True,demo=False)
    window.show(); stage=0; started=time.monotonic(); changed=started; failed=[]
    def check():
        nonlocal stage,changed
        now=time.monotonic()
        try:
            if now-started>20 and stage<3:
                raise AssertionError('Live dashboard did not receive video within 20 seconds')
            if not window.bridge: return
            state=window.last_state
            if stage==0 and window.workspace.live and window.last_sequence>8:
                assert not window.bridge.controller.want_control, 'Dashboard must start as preview only'
                window.control_btn.click(); stage=1; changed=now
            elif stage==1 and now-changed>.7:
                assert window.bridge.controller.want_control, 'Enable button did not enable the session'
                window.stop_btn.click()
                assert not window.bridge.controller.want_control
                window.toggle_showcase(); stage=2; changed=now
            elif stage==2 and now-changed>.5:
                assert not window.bridge.controller.want_control, 'Stop unexpectedly re-enabled'
                window.grab().save(str(Path(__file__).parent/'studio-showcase.png'))
                print('PASS: real Pixel feed inside Qt; enable and stop commands; stop stays latched; Showcase rendering.')
                print('Video:',state.get('width'),state.get('height'),'FPS:',state.get('fps'),'hand:',state.get('selected_hand'))
                print('All mouse output was intercepted by FakeMouse; no physical input injected.')
                stage=3; window.close()
        except Exception as exc:
            failed.append(str(exc)); print('FAIL:',exc); stage=3; window.close()
    timer=QTimer(); timer.timeout.connect(check); timer.start(100)
    app.exec()
    if window.worker: window.worker.join(timeout=3)
    assert not (window.worker and window.worker.is_alive()), 'Tracking thread failed to shut down'
    assert not (window.bridge and window.bridge.camera and window.bridge.camera.process.is_alive()), 'Capture process failed to stop'
    print('PASS: closing Studio stopped tracking and camera capture.')
    return 1 if failed else 0

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
