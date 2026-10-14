from gimp_xtouch import (
    LED_CHANNELS,
    IterableMessageGenerator,
    MidiRelative,
    led_targets,
    process_message,
)


def test_non_button_has_no_led() -> None:
    assert led_targets(15, 186) == []


def test_button_clears_all_led() -> None:
    assert led_targets(16, 186) == [[186, cc, 0] for cc in LED_CHANNELS]


def test_toggleable_button_lights_itself() -> None:
    targets = led_targets(21, 186)
    assert targets[:-1] == [[186, cc, 0] for cc in LED_CHANNELS]
    assert targets[-1] == [186, 21, 127]


def test_process_button_injects_message() -> None:
    btn_map = {3: IterableMessageGenerator([[186, 11, 63]])}
    led, forwarded = process_message(186, 3, 127, btn_map=btn_map)
    assert forwarded == [186, 11, 63]
    assert led == [[186, 11, 63]]


def test_process_encoder_maps_channel() -> None:
    event_map = {15: MidiRelative(incr={65: 80}, decr={63: 82})}
    led, forwarded = process_message(186, 15, 65, event_map=event_map)
    assert forwarded == [186, 80, 65]
    assert led == []
