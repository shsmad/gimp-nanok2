import os

import pytest
import rtmidi

from gimp_xtouch import PORT_SUBSTR_XTOUCH, find_port_by_name

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GIMP_XTOUCH_INTEGRATION"),
        reason="нужен живой X-Touch Mini (задайте GIMP_XTOUCH_INTEGRATION=1)",
    ),
]


def test_xtouch_port_present() -> None:
    midiin = rtmidi.MidiIn()  # type: ignore  # нет стабов у python-rtmidi
    assert find_port_by_name(midiin.get_ports(), PORT_SUBSTR_XTOUCH) != -1
