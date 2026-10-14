from gimp_xtouch import find_port_by_name


def test_find_returns_index() -> None:
    assert find_port_by_name(["A", "X-TOUCH MINI MIDI 1", "B"], "X-TOUCH MINI") == 1


def test_find_missing() -> None:
    assert find_port_by_name(["A", "B"], "GIMP") == -1


def test_find_empty() -> None:
    assert find_port_by_name([], "GIMP") == -1
