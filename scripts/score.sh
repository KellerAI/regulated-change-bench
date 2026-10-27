#!/bin/sh
# Regenerate RESULTS.md and reports/results.json from the published verdicts and keys. Standard library only.
set -eu
cd "$(dirname "$0")/.."
exec python3 scripts/results.py "$@"
