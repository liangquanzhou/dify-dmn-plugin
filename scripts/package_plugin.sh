#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
"${DIFY_CLI:-dify}" plugin package ./plugin -o ./dist/liangquanzhou-dmn_decision-0.3.0-unsigned.difypkg
printf '%s\n' 'UNSIGNED. Administrator review/signing may be required. Keep signature verification enabled.'
