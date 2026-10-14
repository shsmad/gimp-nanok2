# AGENTS.md

MIDI-мост между контроллером Behringer X-Touch Mini и GIMP. Единственный исходник — `src/gimp_xtouch.py`, запускается как скрипт.

## Установка и запуск
- Менеджер зависимостей — PDM (Python `>=3.14`). `pdm install -G dev`.
- venv — `venv/` в корне (`.pdm-python` указывает на него). Запуск: `venv/bin/python src/gimp_xtouch.py` или `./launch-gimp-xtouch.sh` (поднимает GIMP, гасит прошлый мост, стартует мост; порты ждёт супервизор внутри).
- `python-rtmidi` требует системных libasound/LibJack-заголовков — см. `install.md`.
- Логирование: `logging`, логгер `gimpxtouch`; путь/уровень/ротация — `config.toml` `[log]` (env `GIMP_XTOUCH_CONFIG` переопределяет путь конфига, `GIMP_XTOUCH_LOG` — уровень). Пишем в файл (по умолчанию `gimp_xtouch.log` в текущем каталоге) **и** в stderr.

## Lint / typecheck / test
- Lint: `pdm run lint` (`ruff check src tests`, line-length 120).
- Typecheck: `pdm run typecheck` (`ty check`; у `rtmidi` нет стабов — строки помечены `# type: ignore`).
- Тесты: `pdm run test` (`pytest`, `tests/`, `asyncio_mode=auto`; маркер `integration` пропускается без `GIMP_XTOUCH_INTEGRATION`). `[tool:pytest]` в `setup.cfg` устарел — актуален `[tool.pytest.ini_options]` в `pyproject.toml`.

## Особенности
- ВАЖНО: любые гипотезы о поведении и возможностях X-Touch Mini проверять ТОЛЬКО на реальном железе и во взаимодействии с пользователем (не по форумам/докам/аналогиям).
- Имя модуля — `gimp_xtouch.py` (с подчёркиванием): импортируется в тестах (`import gimp_xtouch`) и запускается как скрипт.
- Требуются реальные MIDI-порты с именами, содержащими `X-TOUCH MINI` и `GIMP` (`find_port_by_name`). GIMP должен принимать MIDI (Preferences → Input Devices → MIDI).
- Поток: rtmidi-callback → `loop.call_soon_threadsafe` → `asyncio.Queue`; супервизор `BridgeApp` бесконечно ждёт порты (LED-анимация `bounce`), при готовности — `blink_all` + `snake`, при потере порта переоткрывает.
- Логика разбора — чистые функции `led_targets()`/`process_message()`; карты: `EVENT_MAP` (CC 15 → виртуальные CC 80–83), `BTN_MAP` (CC 3–6), `LED_CHANNELS`/`LED_TOGGLABLE_CHANNELS` (LED 16–31). Всё — константы в коде.
- Карта `controller-<CC>` → действие GIMP живёт в `~/.config/GIMP/3.2/controllerrc` (для GIMP 3.2; перезаписывается GIMP при выходе). Комментарии-карты каналов (LAYER A/B) в шапке `gimp_xtouch.py` документируют раскладку — обновлять их при изменении маппингов.
- Git-операции (в т.ч. коммиты) — за пользователем.
