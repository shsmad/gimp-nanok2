# gimp-nanok2

MIDI-мост между контроллером **Behringer X-Touch Mini** и **GIMP 3.2**: слушает CC
контроллера, транслирует их в нативный MIDI-контроллер GIMP (`ControllerMidi` через
`~/.config/GIMP/3.2/controllerrc`), управляет LED-подсветкой кнопок и переводит
относительный энкодер CC 15 в «виртуальные MIDI-каналы» GIMP.

## Как это работает

```
X-Touch Mini ──(MIDI CC, канал 11)──▶ gimp_xtouch.py ──(MIDI CC)──▶ ControllerMidi (GIMP)
        ▲                                                                    │
        └────────────── LED кнопок (MIDI CC) ◀── локальная логика ◀──────────┘
```

- Большинство CC мост форвардит в GIMP «как есть» — раскладку и действия задаёт
  `controllerrc` самого GIMP (`controller-<CC>` → gimp-команда).
- **Кнопки CC 3–6** инъектят заранее заданное значение в соответствующий
  абсолютный энкодер (`BTN_MAP`) и подсвечивают лампочку на X-Touch.
- **CC 15** (относительный энкодер) переводится в «виртуальные CC» 80–83 (`EVENT_MAP`).
- **Кнопки CC 16–31** управляют LED-строками (`LED_CHANNELS`; переключаемые — 21, 22, 29, 30).
- При отсутствии портов `X-TOUCH MINI` / `GIMP` мост ждёт и переподключается, крутя
  LED-анимацию; при подключении — мигание и «змейка».

## Требования

- Linux (ALSA), Python 3.14, [pdm](https://pdm-project.org/).
- Сборка `python-rtmidi`: `build-essential python3-dev libasound2-dev libjack-jackd2-dev`.
- GIMP 3.2 с включённым MIDI-контроллером: **Preferences → Input Devices → MIDI**.
- Контроллер X-Touch Mini.

## Установка

```bash
pdm install -G dev
```

Подробнее — `install.md`.

## Запуск

```bash
./launch-gimp-xtouch.sh
```

Скрипт поднимает GIMP (если не запущен), гасит прошлый мост и запускает
`src/gimp_xtouch.py`; порты мост ждёт сам.

Напрямую:

```bash
venv/bin/python src/gimp_xtouch.py
```

## `config.toml`

Читается из корня репозитория; путь переопределяется переменной `GIMP_XTOUCH_CONFIG`.

| Ключ `[log]` | По умолчанию | Назначение |
| --- | --- | --- |
| `path` | `gimp_xtouch.log` | Файл лога (относительно текущего каталога). |
| `level` | `DEBUG` | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR`; env `GIMP_XTOUCH_LOG` переопределяет. |
| `max_bytes` | `1000000` | Размер файла до ротации. |
| `backups` | `3` | Число архивных копий. |

Лог всегда пишется **и** в файл, **и** в stderr.

## Раскладка X-Touch Mini (Layer A)

- CC 0–7 — кнопки энкодеров; 8–15 — энкодеры; 16–23 и 24–31 — две строки кнопок; 32 — фейдер.
- CC 3–6 — инъекция значений в энкодеры (`BTN_MAP`); CC 15 — относительный энкодер (`EVENT_MAP`).
- LED — кнопки 16–31; переключаемые — 21, 22, 29, 30.

Карта `controller-<CC>` → действие GIMP живёт в `~/.config/GIMP/3.2/controllerrc`
(перезаписывается GIMP при выходе). Комментарии-карты LAYER A/B — в шапке `src/gimp_xtouch.py`.

## Разработка

```bash
pdm run lint        # ruff check src tests
pdm run typecheck   # ty check
pdm run test        # pytest (интеграционные помечены `integration`, пропуск без env)
```

## Диагностика

- **Порт не найден** — проверьте `aconnect -l`; имена должны содержать `X-TOUCH MINI` и `GIMP`.
  Мост ждёт появления портов и переподключится.
- **Сырой дамп входящих CC** — уровень `DEBUG` (он же уровень по умолчанию) пишет
  в лог каждое пересланное сообщение.
- **Лог** — `gimp_xtouch.log` в текущем каталоге и в stderr.
