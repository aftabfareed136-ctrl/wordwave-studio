from wordwave.timeline import Keyframe, Track


def test_track_interpolates():
    tr = Track([Keyframe(0, 0), Keyframe(1, 100, ease="linear")])
    assert tr.value(0) == 0
    assert tr.value(1) == 100
    assert tr.value(0.5) == 50


def test_track_clamps():
    tr = Track([Keyframe(1, 10), Keyframe(2, 20)])
    assert tr.value(0) == 10
    assert tr.value(5) == 20


def test_track_default():
    assert Track().value(3.3) == 0.0
