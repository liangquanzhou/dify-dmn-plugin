#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
"$PYTHON" -m pytest -q tests/test_plugin.py
"$PYTHON" scripts/check_plugin.py
(cd engine && "${MVN:-mvn}" --batch-mode test package)
"$PYTHON" -m pytest -q tests/test_integration.py
(cd frontend && npm ci && npm test && npm run typecheck && npm run build)
