"""Общие фикстуры; добавляет `src` в sys.path (пакет не устанавливается, distribution=false)."""

from __future__ import annotations

import sys

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


class FakeLed:
    """Заглушка LED-выхода: записывает вызовы set_led (реализует LedSink)."""

    def __init__(self) -> None:
        self.led: list[tuple[int, bool]] = []

    def set_led(self, cc: int, on: bool) -> None:
        self.led.append((cc, on))


@pytest.fixture
def fake_led() -> FakeLed:
    return FakeLed()
