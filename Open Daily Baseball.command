#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python -B scripts/launch_daily_baseball.py
fi
exec python3 -B scripts/launch_daily_baseball.py
