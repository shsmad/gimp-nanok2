import asyncio
import contextlib

from conftest import FakeLed
from gimp_xtouch import LED_CHANNELS, TOP_ROW, blink_all, bounce, snake


async def test_blink_all(fake_led: FakeLed) -> None:
    await blink_all(fake_led, LED_CHANNELS, times=1, on_s=0, off_s=0)
    on = [cc for cc, state in fake_led.led if state]
    off = [cc for cc, state in fake_led.led if not state]
    assert on == list(LED_CHANNELS)
    assert off == list(LED_CHANNELS)


async def test_snake(fake_led: FakeLed) -> None:
    await snake(fake_led, delay=0)
    assert fake_led.led
    assert fake_led.led[0] == (TOP_ROW[0], True)


async def test_bounce_cancels(fake_led: FakeLed) -> None:
    task = asyncio.create_task(bounce(fake_led, delay=0))
    await asyncio.sleep(0)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert any(state for _, state in fake_led.led)
