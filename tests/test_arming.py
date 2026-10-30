from runtime import arm_blocker, ArmRequest

def test_arming_requires_fresh_point_inside_region():
    roi=[.15,.15,.85,.85]
    assert arm_blocker(1,.5,'POINT',(.5,.5),roi)=='Waiting for live video'
    assert 'INDEX' in arm_blocker(1,.9,'PALM',(.5,.5),roi)
    assert 'INSIDE' in arm_blocker(1,.9,'POINT',(.95,.95),roi)
    assert arm_blocker(1,.9,'POINT',(.5,.5),roi)==''
    assert 'ONE' in arm_blocker(1,.9,'MULTIPLE',(.5,.5),roi)
    assert 'full hand' in arm_blocker(1,.9,'LOST',(.5,.5),roi)

def test_arm_request_never_arms_without_keypress():
    a=ArmRequest()
    assert a.update(1,True)=='idle'
    assert a.update(2,True)=='idle'

def test_arm_request_waits_for_stable_ready_pose_then_consumes_request():
    a=ArmRequest(); a.request(1)
    assert a.update(2,False)=='waiting'
    assert a.update(3,True)=='waiting'
    assert a.update(3.2,False)=='waiting'
    assert a.update(4,True)=='waiting'
    assert a.update(4.36,True)=='arm'
    assert a.update(4.8,True)=='idle'

def test_arm_request_expires_and_f8_cancels():
    a=ArmRequest(); a.request(1)
    assert a.update(6,True)=='cancelled'
    assert a.update(7,True)=='idle'
    a.request(8)
    assert a.update(8.1,True,emergency=True)=='cancelled'
    assert a.update(9,True)=='idle'
