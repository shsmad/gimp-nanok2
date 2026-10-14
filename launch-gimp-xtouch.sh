#!/usr/bin/env bash
# Запуск GIMP и MIDI-моста gimp-xtouch.
# GIMP поднимается, если ещё не запущен; прошлый экземпляр моста гасится;
# мост сам ждёт появления портов X-TOUCH MINI и GIMP (супервизор).
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/venv/bin/python"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3)"
fi

if ! pgrep -x gimp >/dev/null 2>&1; then
    /usr/bin/gimp "$@" &
fi

pkill -f gimp_xtouch.py 2>/dev/null || true

exec "$PY" "$DIR/src/gimp_xtouch.py"
