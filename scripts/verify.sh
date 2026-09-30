#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
"${PYTHON:-python3}" -m pytest -q tests
"${PYTHON:-python3}" scripts/check_plugin.py
"${PYTHON:-python3}" tests/compatibility/stdio_smoke.py --output /tmp/dmn-v030-stdio-evidence.json
