import time

from dataclasses import dataclass

import rtmidi

from rtmidi.midiutil import open_midiinput, open_midioutput


def find_port_by_name(ports: list[str], name: str) -> int:
    return next((idx for idx, port in enumerate(ports) if name in port), -1)


@dataclass
class MidiRelative:
    incr: dict[int, int]
    decr: dict[int, int]

    def virtual_midi_channel(self, value: int) -> int:
        if value <= max(self.decr.keys()):
            sorted_keys = sorted(self.decr.keys())
            for key in sorted_keys:
                if value <= key:
                    return self.decr[key]
            return self.decr[sorted_keys[0]]

        if value >= min(self.incr.keys()):
            sorted_keys = sorted(self.incr.keys(), reverse=True)
            for key in sorted_keys:
                if value >= key:
                    return self.incr[key]
            return self.incr[sorted_keys[-1]]

        return value


class IterableMessageGenerator:
    def __init__(self, messages: list[list[int]]):
        self.messages = messages
        self.index = 0

    def __iter__(self):
        return self

    def __next__(self):
        value = self.messages[self.index]
        self.index = (self.index + 1) % len(self.messages)
        return value


"""
https://www.midi.org/specifications-old/item/table-2-expanded-messages-list-status-bytes
138 	Chan 11 Note off 	Note Number (0-127) 	Note Velocity (0-127)
154 	Chan 11 Note on 	Note Number (0-127) 	Note Velocity (0-127)
170 	Chan 11 Polyphonic Aftertouch 	Note Number (0-127 	Pressure (0-127)
186 	Chan 11 Control/Mode Change 	see Table 3 	see Table 3
202 	Chan 11 Program Change 	Program # (0-127) 	none
218 	Chan 11 Channel Aftertouch 	Pressure (0-127) 	none
234 	Chan 11 Pitch Bend Change 	Pitch Bender LSB (0-127) 	Pitch Bender MSB (0-127)
"""

# relative1 = [127-;1=]
# relative2 = [63-;65+]
# relative3 = [65-;1+]

# MAX_MIDI_CHANNEL = [0-32] + [33-65] = 65
# VIRTUAL_MIDI_CHANNELS should start from 66
# LAYER A
# knob buttons: [E E E view-rotate-set-absolute tools-hardness-set context-opacity-set view-zoom tools-size-set-to-default] = [0-7]  # noqa: E501
# knobs: [E E E view-rotate-set-absolute tools-hardness-set context-opacity-set view-zoom BrushSize(R2)] = [8-15]
# row1: [dialogs-tool-options edit-undo edit-redo E layers-new-from-visible tools-paintbrush tools-smudge drawable-visible] = [16-23]  # noqa: E501
# row2: [dialogs-dynamics E E E image-resize-to-layers tools-clone tools-heal context-colors-swap] = [24-31]
# fader: [E] = [32]

# LAYER B
# knob buttons:
# knobs:
# row1:
# row2:
# fader:

LED_CHANNELS = tuple(range(16, 24)) + tuple(range(24, 32))  # button row1 + row2
LED_TOGGLABLE_CHANNELS = (21, 22, 29, 30)  # [186, 21, 0/1]

EVENT_MAP = {
    15: MidiRelative(incr={65: 80, 67: 81}, decr={63: 82, 61: 83}),  # brush size
}


BTN_MAP = {
    # 25% - 32, 50% - 63, 100% - 127
    3: IterableMessageGenerator(messages=[[186, 11, 63]]),  # rotate
    4: IterableMessageGenerator(messages=[[186, 12, 127], [186, 12, 32]]),  # hardness
    5: IterableMessageGenerator(messages=[[186, 13, 127]]),  # opacity
    6: IterableMessageGenerator(messages=[[186, 14, 63]]),  # zoom
}


class InputCallback:
    def __init__(self, out_port, led_port):
        self.out_port = out_port
        self.led_port = led_port

    def __call__(self, event, data=None):
        """
        event: (MIDI message, delta time in seconds elapsed since the reception of previous event)
        data: passed to set_callback
        example: ([176, 22, 3], 0.023500365000000002), None
        """

        message, delta = event
        # print(f"[->] {message}")

        channel_no, midi_value = message[1], message[2]

        if channel_no in LED_CHANNELS:
            # turn off all leds
            for led in LED_CHANNELS:
                self.led_port.send_message([message[0], led, 0])

            # only turn on led if it's for toggleable channels
            if channel_no in LED_TOGGLABLE_CHANNELS:
                self.led_port.send_message([message[0], channel_no, 127])

        if channel_no in BTN_MAP:
            message_generator = BTN_MAP[channel_no]
            new_message = next(message_generator)
            self.led_port.send_message(new_message)
            # print(message, new_message)
            message[1] = new_message[1]
            message[2] = new_message[2]
            # print(message, new_message)

        if channel_no in EVENT_MAP:
            channel_no = EVENT_MAP[channel_no].virtual_midi_channel(midi_value)
            message[1] = channel_no

        print(f"[>-] {message}")

        self.out_port.send_message(message)


def run():
    midiin = rtmidi.MidiIn()
    midiout = rtmidi.MidiOut()
    print(midiin.get_ports())
    print(midiout.get_ports())

    xt_port_idx = find_port_by_name(midiin.get_ports(), "X-TOUCH MINI")
    print(f"{xt_port_idx=}")
    led_port_idx = find_port_by_name(midiout.get_ports(), "X-TOUCH MINI")
    print(f"{led_port_idx=}")
    gimp_port_idx = find_port_by_name(midiout.get_ports(), "GIMP")
    print(f"{gimp_port_idx=}")

    led_port = open_midioutput(port=led_port_idx, client_name="gimp-xtouch")
    xt_port = open_midiinput(port=xt_port_idx, client_name="gimp-xtouch")
    gimp_port = open_midioutput(port=gimp_port_idx, client_name="gimp-xtouch")
    xt_port[0].set_callback(InputCallback(out_port=gimp_port[0], led_port=led_port[0]))


if __name__ == "__main__":
    run()
    while True:
        time.sleep(0.01)
