import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
import pytest
from PySide6.QtWidgets import QApplication
from dashboard_bridge import DashboardBridge
from engine import Controller
from config import validate
from selftest import FakeMouse

@pytest.fixture(scope='module')
def qt():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def studio(qt,monkeypatch):
    import desktop
    monkeypatch.setattr(desktop,'save',lambda config:None)
    w=desktop.Studio(autoconnect=False,demo=True)
    yield w
    w.pending_settings.clear()
    w.worker=None; w.close(); qt.processEvents()

def attach(w):
    w.bridge=DashboardBridge()
    w.bridge.controller=Controller(validate({'auto_resume':True}),FakeMouse())
    w.worker=SimpleNamespace(is_alive=lambda:True)
    return w.bridge

def test_stop_discards_queued_resume_preserves_settings_and_releases_drag():
    bridge=DashboardBridge(); mouse=FakeMouse()
    bridge.controller=Controller(validate({}),mouse)
    bridge.controller.dragging=True
    bridge.send('resume'); bridge.send('settings',{'smoothing':.03})
    bridge.pause()
    assert bridge.drain()==[('settings',{'smoothing':.03}),('pause',None)]
    assert mouse.events==[('up',)] and not bridge.controller.want_control

def test_ui_buttons_send_real_commands(studio):
    bridge=attach(studio)
    studio.control_btn.click()
    assert bridge.drain()==[('resume',None)]
    studio.switch_btn.click()
    assert bridge.drain()==[('switch',None)]
    studio.stop_btn.click()
    assert not bridge.controller.want_control
    assert bridge.drain()==[('pause',None)]

def test_live_settings_and_full_gestures_stop_first(studio):
    bridge=attach(studio)
    studio.smoothing.setValue(45); studio.flush_settings()
    assert bridge.drain()==[('settings',{'smoothing':.045})]
    studio.toggles['cursor_only'].setChecked(False); studio.flush_settings()
    actions=bridge.drain()
    assert actions[0][0]=='pause' and actions[-1]==('settings',{'cursor_only':False})

def test_calibration_can_cancel_and_stays_paused(studio):
    bridge=attach(studio); studio.workspace.live=True
    studio.calibrate(); assert studio.workspace.calibrating
    studio.calibrate(); assert not studio.workspace.calibrating
    assert not bridge.controller.want_control

def test_showcase_and_navigation(studio,qt):
    studio.show(); qt.processEvents()
    studio.navigate(1); assert studio.pages.currentIndex()==1
    studio.toggle_showcase()
    assert studio.workspace.showcase and studio.pages.currentIndex()==0
    for toggle in studio.toggles.values():
        assert toggle.width()>=toggle.sizeHint().width()

def test_bridge_publishes_without_recording():
    bridge=DashboardBridge(); frame=object()
    bridge.publish(frame=frame,state={'enabled':False},geometry=[{'points':[]}])
    sequence,image,state,updated,geometry=bridge.snapshot()
    assert sequence==1 and image is frame and state=={'enabled':False}
    assert geometry==[{'points':[]}]
