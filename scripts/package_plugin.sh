#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
DIFY_CLI="${DIFY_CLI:-dify}"
"$DIFY_CLI" plugin package ./plugin -o ./dist/liangquanzhou-dmn_decision-0.1.1-unsigned.difypkg
printf '%s\n' 'UNSIGNED package only. Administrator review/signing is required; keep signature verification enabled.'
