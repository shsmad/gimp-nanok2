from gimp_xtouch import IterableMessageGenerator, MidiRelative

SCHEME = MidiRelative(incr={65: 80, 67: 81}, decr={63: 82, 61: 83})


def test_incr_values() -> None:
    assert SCHEME.virtual_midi_channel(65) == 80
    assert SCHEME.virtual_midi_channel(67) == 81
    assert SCHEME.virtual_midi_channel(127) == 81


def test_decr_values() -> None:
    assert SCHEME.virtual_midi_channel(63) == 82
    assert SCHEME.virtual_midi_channel(61) == 83
    assert SCHEME.virtual_midi_channel(0) == 83


def test_dead_zone_passthrough() -> None:
    # 64 не описано ни в incr, ни в decr -> значение уходит как есть (в controllerrc нет записи)
    assert SCHEME.virtual_midi_channel(64) == 64


def test_generator_cycles() -> None:
    gen = IterableMessageGenerator([[1, 2, 3], [4, 5, 6]])
    assert [next(gen) for _ in range(4)] == [[1, 2, 3], [4, 5, 6], [1, 2, 3], [4, 5, 6]]
