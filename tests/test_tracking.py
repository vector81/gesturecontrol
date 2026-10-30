from types import SimpleNamespace as NS
from tracking import HandSelector

ROI=[.15,.15,.85,.85]

def hand(x,y=.5):
    return [NS(x=x,y=y) for _ in range(21)]

def label(name,score=.99):
    return [NS(category_name=name,score=score)]

def test_acquires_central_hand_then_ignores_model_order_and_other_hand():
    s=HandSelector()
    assert s.select([hand(.7),hand(.5)],[label('Left'),label('Right')],ROI)==1
    assert s.label=='Right'
    assert s.select([hand(.51),hand(.5)],[label('Right'),label('Left')],ROI)==0

def test_selected_hand_leaving_never_transfers_control():
    s=HandSelector()
    s.select([hand(.5)],[label('Right')],ROI)
    assert s.select([hand(.5)],[label('Left')],ROI) is None
    assert s.label=='Right'
    assert s.select([hand(.51),hand(.55)],[label('Left'),label('Right')],ROI)==1

def test_switch_changes_hand_explicitly():
    s=HandSelector()
    s.select([hand(.5)],[label('Right')],ROI)
    s.switch()
    assert s.select([hand(.5),hand(.7)],[label('Right'),label('Left')],ROI)==1

def test_ambiguous_same_label_and_low_confidence_wait():
    s=HandSelector()
    s.select([hand(.5)],[label('Right')],ROI)
    assert s.select([hand(.48),hand(.52)],[label('Right'),label('Right')],ROI) is None
    assert s.select([hand(.5)],[label('Right',.4)],ROI) is None

def test_duplicate_label_uses_continuity_if_unambiguous():
    s=HandSelector()
    s.select([hand(.5)],[label('Right')],ROI)
    assert s.select([hand(.8),hand(.51)],[label('Right'),label('Right')],ROI)==1

def test_no_initial_selection_outside_work_area():
    s=HandSelector()
    assert s.select([hand(.95)],[label('Right')],ROI) is None
    assert s.label is None

def test_empty_or_missing_handedness_waits():
    s=HandSelector()
    assert s.select([],[],ROI) is None
    assert s.select([hand(.5)],[],ROI) is None
