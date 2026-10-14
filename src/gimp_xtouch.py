"""MIDI-мост между контроллером Behringer X-Touch Mini и GIMP.

Запуск: `python src/gimp_xtouch.py`.

Скрипт слушает CC контроллера, транслирует их в GIMP (нативный MIDI-контроллер
`ControllerMidi` через `controllerrc`), управляет LED-подсветкой кнопок и
переводит относительный энкодер в «виртуальные MIDI-каналы». При недоступности
портов X-TOUCH MINI / GIMP — ждёт и переподключается.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import tomllib

from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

import rtmidi

logger = logging.getLogger("gimpxtouch")

PORT_SUBSTR_XTOUCH = "X-TOUCH MINI"
PORT_SUBSTR_GIMP = "GIMP"
# Control Change на MIDI-канале 11 (1-based): 0xB0 + 10 = 0xBA = 186.
CC_STATUS = 0xBA
RETRY_SECONDS = 2.0  # пауза между попытками (пере)подключения портов


def find_port_by_name(ports: list[str], name: str) -> int:
    """Индекс первого порта, чьё имя содержит подстроку; -1 если нет."""
    return next((idx for idx, port in enumerate(ports) if name in port), -1)


@dataclass
class MidiRelative:
    """Перевод сырого значения относительного энкодера в «виртуальный CC» GIMP."""

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
    """Бесконечный цикл по списку MIDI-сообщений (для кнопок-переключателей)."""

    def __init__(self, messages: list[list[int]]):
        self.messages = messages
        self.index = 0

    def __iter__(self) -> IterableMessageGenerator:
        return self

    def __next__(self) -> list[int]:
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

TOP_ROW = tuple(range(16, 24))  # 16..23
BOTTOM_ROW = tuple(range(24, 32))  # 24..31

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


def led_targets(channel_no: int, status: int) -> list[list[int]]:
    """LED-команды X-Touch на входящее сообщение строки кнопок (16..31).

    Гасим все LED, затем зажигаем нажатый, если он из переключаемых. Для прочих
    каналов LED не трогаем.
    """
    if channel_no not in LED_CHANNELS:
        return []
    targets = [[status, led, 0] for led in LED_CHANNELS]
    if channel_no in LED_TOGGLABLE_CHANNELS:
        targets.append([status, channel_no, 127])
    return targets


def process_message(
    status: int,
    channel_no: int,
    midi_value: int,
    *,
    btn_map: dict[int, IterableMessageGenerator] = BTN_MAP,
    event_map: dict[int, MidiRelative] = EVENT_MAP,
) -> tuple[list[list[int]], list[int]]:
    """Разобрать входящее сообщение: (LED-команды, сообщение для GIMP)."""
    led_messages = led_targets(channel_no, status)
    forwarded = [status, channel_no, midi_value]

    if channel_no in btn_map:
        new_message = next(btn_map[channel_no])
        led_messages.append(list(new_message))
        forwarded[1] = new_message[1]
        forwarded[2] = new_message[2]

    if channel_no in event_map:
        forwarded[1] = event_map[channel_no].virtual_midi_channel(midi_value)

    return led_messages, forwarded


@dataclass(frozen=True)
class LogSpec:
    """Настройки логирования из `[log]`."""

    path: str = "gimp_xtouch.log"
    level: str = "DEBUG"
    max_bytes: int = 1_000_000
    backups: int = 3


@dataclass(frozen=True)
class Config:
    log: LogSpec


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.toml"


def default_config_path() -> Path:
    """Путь к config.toml по умолчанию либо из `GIMP_XTOUCH_CONFIG`."""
    override = os.environ.get("GIMP_XTOUCH_CONFIG")
    if override:
        return Path(override).expanduser()
    return DEFAULT_CONFIG_PATH


def _parse_log(raw: object) -> LogSpec:
    if not isinstance(raw, dict):
        raise ValueError("[log] должен быть таблицей")
    path = raw.get("path", "gimp_xtouch.log")
    if not isinstance(path, str) or not path:
        raise ValueError("[log] path должен быть непустой строкой")
    level = raw.get("level", "DEBUG")
    if not isinstance(level, str) or not level:
        raise ValueError("[log] level должен быть непустой строкой")
    try:
        max_bytes = int(raw.get("max_bytes", 1_000_000))
        backups = int(raw.get("backups", 3))
    except (TypeError, ValueError) as exc:
        raise ValueError("[log] max_bytes/backups должны быть целыми") from exc
    if max_bytes <= 0 or backups < 0:
        raise ValueError("[log] max_bytes > 0, backups >= 0")
    return LogSpec(path=path, level=level.upper(), max_bytes=max_bytes, backups=backups)


def load_config(path: str | Path | None = None) -> Config:
    """Прочитать и провалидировать конфиг из TOML."""
    chosen = Path(path) if path else default_config_path()
    if not chosen.exists():
        raise FileNotFoundError(f"config.toml не найден: {chosen}")
    with chosen.open("rb") as handle:
        data = tomllib.load(handle)
    return Config(log=_parse_log(data.get("log", {})))


def configure_logging(spec: LogSpec) -> None:
    """Лог в stderr и в файл; env `GIMP_XTOUCH_LOG` переопределяет уровень."""
    level_name = os.environ.get("GIMP_XTOUCH_LOG", spec.level).strip().upper()
    level = getattr(logging, level_name, logging.DEBUG)
    log_path = Path(spec.path).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    root = logging.getLogger("gimpxtouch")
    root.handlers.clear()
    root.setLevel(level)
    root.propagate = False

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(fmt)
    root.addHandler(stderr)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=spec.max_bytes, backupCount=spec.backups, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


class LedSink(Protocol):
    def set_led(self, cc: int, on: bool) -> None: ...


class XTouch:
    """Вход (события) и LED-выход X-Touch Mini; события кладёт в очередь."""

    def __init__(
        self,
        events: asyncio.Queue[tuple[int, int, int]],
        loop: asyncio.AbstractEventLoop,
        *,
        client_name: str = "gimp-xtouch",
    ) -> None:
        self._events = events
        self._loop = loop
        self._name = client_name
        self._opened = False
        self._midiin = rtmidi.MidiIn()  # type: ignore  # нет стабов у python-rtmidi
        self._midiout = rtmidi.MidiOut()  # type: ignore  # нет стабов у python-rtmidi

    def open(self) -> None:
        in_idx = find_port_by_name(self._midiin.get_ports(), PORT_SUBSTR_XTOUCH)
        if in_idx == -1:
            raise RuntimeError(f"MIDI-вход '{PORT_SUBSTR_XTOUCH}' не найден: {self._midiin.get_ports()}")
        out_idx = find_port_by_name(self._midiout.get_ports(), PORT_SUBSTR_XTOUCH)
        if out_idx == -1:
            raise RuntimeError(f"MIDI-выход '{PORT_SUBSTR_XTOUCH}' не найден: {self._midiout.get_ports()}")
        self._midiin.open_port(in_idx, self._name)
        self._midiout.open_port(out_idx, self._name)
        self._midiin.set_callback(self._on_event)
        self._opened = True

    def is_open(self) -> bool:
        return self._opened and find_port_by_name(self._midiin.get_ports(), PORT_SUBSTR_XTOUCH) != -1

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._midiin.cancel_callback()
        with contextlib.suppress(Exception):
            self._midiin.close_port()
        with contextlib.suppress(Exception):
            self._midiout.close_port()
        self._opened = False

    def set_led(self, cc: int, on: bool) -> None:
        """LED кнопки: CC value 127 вкл / 0 выкл."""
        if self._opened:
            self._midiout.send_message([CC_STATUS, cc, 127 if on else 0])

    def send_led_raw(self, message: list[int]) -> None:
        if self._opened:
            self._midiout.send_message(message)

    def _on_event(self, event: tuple[list[int], float], data: object = None) -> None:
        message, _delta = event
        if len(message) < 3:
            return
        status, cc, value = message[0], message[1], message[2]
        # callback rtmidi идёт из своего потока -> в очередь event loop потокобезопасно
        self._loop.call_soon_threadsafe(self._events.put_nowait, (status, cc, value))


class GimpOut:
    """Выход к GIMP (его MIDI-контроллер `ControllerMidi`)."""

    def __init__(self, *, client_name: str = "gimp-xtouch") -> None:
        self._name = client_name
        self._opened = False
        self._midiout = rtmidi.MidiOut()  # type: ignore  # нет стабов у python-rtmidi

    def open(self) -> None:
        idx = find_port_by_name(self._midiout.get_ports(), PORT_SUBSTR_GIMP)
        if idx == -1:
            raise RuntimeError(f"MIDI-выход '{PORT_SUBSTR_GIMP}' не найден: {self._midiout.get_ports()}")
        self._midiout.open_port(idx, self._name)
        self._opened = True

    def is_open(self) -> bool:
        return self._opened and find_port_by_name(self._midiout.get_ports(), PORT_SUBSTR_GIMP) != -1

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._midiout.close_port()
        self._opened = False

    def send(self, message: list[int]) -> None:
        if self._opened:
            self._midiout.send_message(message)


async def blink_all(
    led: LedSink,
    ccs: tuple[int, ...] = LED_CHANNELS,
    *,
    times: int = 2,
    on_s: float = 0.12,
    off_s: float = 0.12,
) -> None:
    """Мигнуть всеми указанными LED `times` раз."""
    for _ in range(times):
        for cc in ccs:
            led.set_led(cc, True)
        await asyncio.sleep(on_s)
        for cc in ccs:
            led.set_led(cc, False)
        await asyncio.sleep(off_s)


async def snake(
    led: LedSink,
    *,
    top: tuple[int, ...] = TOP_ROW,
    bottom: tuple[int, ...] = BOTTOM_ROW,
    delay: float = 0.06,
) -> None:
    """Змейка: вправо по верхнему ряду (16→23), затем влево по нижнему (31→24)."""
    for row in (top, bottom):
        previous: int | None = None
        for cc in row:
            led.set_led(cc, True)
            if previous is not None:
                led.set_led(previous, False)
            previous = cc
            await asyncio.sleep(delay)
        if previous is not None:
            led.set_led(previous, False)


async def bounce(
    led: LedSink,
    ccs: tuple[int, ...] = TOP_ROW,
    *,
    delay: float = 0.08,
) -> None:
    """Бегущая точка «туда-обратно» по ряду; крутится до отмены задачи."""
    row = list(ccs) or [TOP_ROW[0]]
    ping = row + row[-2:0:-1] if len(row) >= 2 else row
    previous: int | None = None
    while True:
        for cc in ping:
            led.set_led(cc, True)
            if previous is not None:
                led.set_led(previous, False)
            previous = cc
            await asyncio.sleep(delay)


class BridgeApp:
    """Супервизор: ждёт порты, крутит анимации, разбирает поток CC."""

    def __init__(
        self,
        xtouch: XTouch,
        gimp: GimpOut,
        events: asyncio.Queue[tuple[int, int, int]],
    ) -> None:
        self._xtouch = xtouch
        self._gimp = gimp
        self._events = events

    async def run(self) -> None:
        logger.info("запуск моста gimp-xtouch")
        try:
            while True:
                await self._wait_for_ports()
                logger.info("порты открыты")
                await blink_all(self._xtouch)
                await snake(self._xtouch)
                await self._event_loop()
        finally:
            self._xtouch.close()
            self._gimp.close()

    async def _wait_for_ports(self) -> None:
        """Открывать порты до успеха; пока ждём — крутить bounce."""
        bounce_task = asyncio.create_task(bounce(self._xtouch))
        try:
            while not (self._xtouch.is_open() and self._gimp.is_open()):
                self._try_open(self._xtouch, "X-TOUCH MINI")
                self._try_open(self._gimp, "GIMP")
                if self._xtouch.is_open() and self._gimp.is_open():
                    break
                await asyncio.sleep(RETRY_SECONDS)
        finally:
            bounce_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bounce_task

    @staticmethod
    def _try_open(port: XTouch | GimpOut, label: str) -> None:
        if port.is_open():
            return
        try:
            port.close()
            port.open()
            logger.info("порт '%s' открыт", label)
        except RuntimeError as exc:
            logger.warning("порт '%s' недоступен: %s", label, exc)

    async def _event_loop(self) -> None:
        """Обрабатывать события, периодически проверяя наличие портов."""
        while True:
            if not (self._xtouch.is_open() and self._gimp.is_open()):
                logger.warning("порт потерян — переподключение")
                return
            try:
                status, cc, value = await asyncio.wait_for(self._events.get(), timeout=RETRY_SECONDS)
            except TimeoutError:
                continue
            led_messages, forwarded = process_message(status, cc, value)
            for message in led_messages:
                self._xtouch.send_led_raw(message)
            logger.debug("CC %d=%d -> %s", cc, value, forwarded)
            self._gimp.send(forwarded)


async def _run_async() -> None:
    config = load_config()
    configure_logging(config.log)
    logger.info("config: %s; log: %s", default_config_path(), config.log.path)
    events: asyncio.Queue[tuple[int, int, int]] = asyncio.Queue()
    xtouch = XTouch(events, asyncio.get_running_loop())
    gimp = GimpOut()
    app = BridgeApp(xtouch, gimp, events)
    await app.run()


def main() -> int:
    try:
        asyncio.run(_run_async())
    except KeyboardInterrupt:
        logger.info("остановлен по Ctrl+C")
        return 0
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
