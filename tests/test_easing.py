from wordwave import easing


def test_bounds():
    for name, fn in easing.EASES.items():
        assert abs(fn(0.0) - 0.0) < 1e-9, name
        assert abs(fn(1.0) - 1.0) < 1e-9, name


def test_clamp():
    assert easing.get("linear")(-5) == 0.0
    assert easing.get("linear")(99) == 1.0


def test_back_overshoots():
    # the "pop" ease must overshoot 1 mid-flight, like AE's overshoot
    assert easing.ease_out_back(0.7) > 1.0


def test_unknown_ease():
    try:
        easing.get("nope")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
