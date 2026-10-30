import math
from types import SimpleNamespace
import pytest
from config import validate
from engine import Controller, classify
from selftest import FakeMouse

def make(**kw):
    out=FakeMouse()
    engine=Controller(validate({'cursor_only':False, **kw}),out)
    engine.arm(0)
    return engine,out

def hold(e,gesture,t,point=(.5,.5)):
    e.update(gesture,point,t)
    e.update(gesture,point,t+.4)

def test_starts_paused():
    m=FakeMouse(); e=Controller(validate({}),m)
    hold(e,'POINT',0); hold(e,'PINCH',1)
    assert not e.enabled and not m.events

def test_pinch_requires_point_and_only_clicks_once():
    e,m=make()
    hold(e,'PINCH',0)
    assert not m.events
    hold(e,'POINT',1); hold(e,'PINCH',2)
    for t in (3,4,5): e.update('PINCH',(.5,.5),t)
    assert m.events==[('click',)]
    hold(e,'POINT',6); hold(e,'PINCH',7)
    assert m.events==[('click',),('click',)]

def test_short_pose_and_cooldown():
    e,m=make(click_cooldown=2)
    hold(e,'POINT',0); hold(e,'PINCH',.5)
    hold(e,'POINT',1); hold(e,'PINCH',1.5)
    assert m.events==[('click',)]
    e.update('POINT',(.5,.5),3); hold(e,'PINCH',3.05)
    assert m.events==[('click',)]

@pytest.mark.parametrize('reason',['PALM','LOST','MULTIPLE'])
def test_safety_releases_drag_and_latches(reason):
    e,m=make(); hold(e,'FIST',0)
    assert e.dragging
    e.update(reason,(.5,.5),1)
    hold(e,'POINT',2); hold(e,'PINCH',3)
    assert m.events==[('down',),('up',)]
    assert not e.enabled

def test_unknown_releases_drag_immediately():
    e,m=make(); hold(e,'FIST',0)
    e.update('UNKNOWN',(.5,.5),.41)
    assert not e.dragging and m.events[-1]==('up',)

def test_watchdog_and_emergency():
    e,m=make(); hold(e,'FIST',0)
    e.watchdog(.91)
    assert not e.enabled and m.events[-1]==('up',)
    e.arm(1); hold(e,'FIST',1)
    e.disable('EMERGENCY F8')
    assert not e.enabled and m.events[-1]==('up',)

def test_cursor_only_suppresses_all_buttons():
    e,m=make(cursor_only=True)
    hold(e,'POINT',0); hold(e,'PINCH',1); hold(e,'FIST',2)
    hold(e,'SCROLL',3); e.update('SCROLL',(.5,.4),3.5)
    assert not m.events

def test_cursor_smooth_speed_limited_and_reanchors():
    e,m=make(max_speed=500)
    hold(e,'POINT',0)
    e.update('POINT',(.53,.5),.42)
    assert 960 < m.xy[0] <= 970
    assert m.xy[1]==540
    e.disable(); e.arm(1); hold(e,'POINT',1, (.7,.7))
    assert len(m.events)==1  # no snap on re-arm at a different point

def test_jump_disables_and_outside_roi_does_not_move():
    e,m=make(); hold(e,'POINT',0)
    e.update('POINT',(.9,.5),.5)
    assert not m.events and not e.enabled
    e.arm(.6)
    hold(e,'POINT',.6)
    e.update('POINT',(.7,.5),1.1)
    assert not e.enabled and not m.events

@pytest.mark.parametrize('gesture',['PINCH','FIST','SCROLL'])
def test_gestures_outside_calibration_never_actuate(gesture):
    e,m=make(); hold(e,'POINT',0)
    hold(e,gesture,1,(.95,.5))
    assert not e.enabled and not m.events

def test_scroll_has_anchor_and_bounded_ticks():
    e,m=make(); hold(e,'SCROLL',0)
    assert not m.events
    e.update('SCROLL',(.5,.45),.5)
    assert m.events==[('scroll',1)]
    hold(e,'POINT',1)
    hold(e,'SCROLL',2,(.5,.2))
    assert m.events==[('scroll',1)]

@pytest.mark.parametrize('raw',[{'sensitivity':float('nan')},{'source':'http://8.8.8.8/video'},
                               {'pinch_on':.5,'pinch_off':.3},{'roi':[0,0,.1,.1]},
                               {'smoothing':-.01},{'cursor_only':'false'}])
def test_invalid_config(raw):
    with pytest.raises(ValueError): validate(raw)

def synthetic_hand(extended):
    # Palm facing camera, fingers pointing upward; bent tips fold toward wrist.
    p=[SimpleNamespace(x=.5,y=.8) for _ in range(21)]
    p[0]=SimpleNamespace(x=.5,y=.9)
    p[4]=SimpleNamespace(x=.16,y=.65)
    for base,x,on in zip((5,9,13,17),(.38,.48,.58,.68),extended):
        for j,y in enumerate((.65,.48,.36,.23) if on else (.65,.55,.67,.76)):
            p[base+j]=SimpleNamespace(x=x,y=y)
    return p

@pytest.mark.parametrize('extended,expected',[([1,0,0,0],'POINT'),([1,1,0,0],'SCROLL'),
                                             ([1,1,1,1],'PALM'),([0,0,0,0],'FIST'),
                                             ([0,1,0,0],'UNKNOWN')])
def test_landmark_classification(extended,expected):
    p=synthetic_hand(extended)
    assert classify(p,4/3,validate({}))[0]==expected

def test_pinch_hysteresis():
    p=synthetic_hand([1,0,0,0]); p[4]=SimpleNamespace(x=p[8].x+.09,y=p[8].y)
    c=validate({})
    assert classify(p,1,c,True)[0]=='PINCH'
    assert classify(p,1,c,False)[0]=='POINT'

def test_palm_rotation_invariant():
    p=synthetic_hand([1,1,1,1])
    for q in p: q.x,q.y=1-q.y,q.x
    assert classify(p,1,validate({}))[0]=='PALM'

@pytest.mark.parametrize('pose',[[1,1,1,1],[1,1,0,0],[0,0,0,0],[1,0,1,0]])
def test_relaxed_cursor_uses_fingertip_without_folded_pose(pose):
    p=synthetic_hand(pose)
    c=validate({'relaxed_pose':True,'cursor_only':True})
    gesture,point,_=classify(p,1,c)
    assert gesture=='POINT'
    assert point==(p[8].x,p[8].y)
    c['cursor_only']=False
    if all(pose): assert classify(p,1,c)[0]=='PALM'

def test_absolute_position_has_no_anchor_offset_or_drift():
    e,m=make(absolute_cursor=True,smoothing=0)
    hold(e,'POINT',0,(.325,.325))
    assert m.xy==(480,270)
    e.update('POINT',(.675,.675),.5)
    assert m.xy==(1439,809)
    e.update('POINT',(.325,.325),.6)
    assert m.xy==(480,270)
    e.disable(); m.xy=(100,100); e.arm(1)
    hold(e,'POINT',1,(.325,.325))
    assert m.xy==(480,270)

@pytest.mark.parametrize('interruption',['LOST','MULTIPLE','PALM','OUTSIDE','WATCHDOG'])
def test_automatic_resume_after_interruption(interruption):
    e,m=make(auto_resume=True,absolute_cursor=True,smoothing=0)
    hold(e,'POINT',0)
    if interruption=='OUTSIDE': e.update('POINT',(.99,.99),.5)
    elif interruption=='WATCHDOG': e.watchdog(1)
    else: e.update(interruption,(.5,.5),.5)
    assert not e.enabled and e.want_control
    before=len(m.events)
    e.update('POINT',(.5,.5),2)
    assert not e.enabled and len(m.events)==before
    e.update('POINT',(.5,.5),2.3)
    e.update('POINT',(.5,.5),2.6)
    assert e.enabled and len(m.events)>before

def test_emergency_and_manual_pause_never_auto_resume():
    e,m=make(auto_resume=True)
    for reason in ('EMERGENCY F8','PAUSED','CALIBRATING'):
        e.disable(reason)
        hold(e,'POINT',1); hold(e,'POINT',2)
        assert not e.enabled and not e.want_control
        e.suspend('VIDEO UNAVAILABLE')
        hold(e,'POINT',3)
        assert not e.enabled and not e.want_control

def test_auto_resume_releases_drag_and_requires_pointer_before_actions():
    e,m=make(auto_resume=True)
    hold(e,'FIST',0)
    e.update('LOST',(0,0),.5)
    assert m.events==[('down',),('up',)]
    hold(e,'FIST',1); hold(e,'PINCH',2)
    assert not e.enabled and m.events==[('down',),('up',)]
