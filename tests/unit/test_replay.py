from nls.replay import ReplayWindow

def test_replay_window_accepts_out_of_order_once():
    w = ReplayWindow(8)
    assert w.accept(10); assert w.accept(8); assert not w.accept(8)
    assert w.accept(11); assert not w.accept(10)

def test_replay_window_rejects_too_old_and_negative():
    w = ReplayWindow(4)
    assert w.accept(5); assert w.accept(10)
    assert not w.accept(5); assert not w.accept(-1)
