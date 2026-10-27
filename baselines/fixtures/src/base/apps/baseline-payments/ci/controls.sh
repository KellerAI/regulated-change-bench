#!/bin/sh
set -eu
out=$(cd "$1" && pwd)
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" -m pytest -q -p no:cacheprovider -m control --junitxml="$out/payments-controls.xml" tests/controls
