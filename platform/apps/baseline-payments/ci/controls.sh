#!/bin/sh
# Usage: ci/controls.sh <out-dir>   Control tests only; JUnit XML into <out-dir>.
set -eu
. "$(cd "$(dirname "$0")" && pwd)/env.sh"
out=$(out_dir_arg "$@")
cd "$app_dir"
exec "$PYTHON" -m pytest -q -p no:cacheprovider -m control \
    -o junit_suite_name=payments-controls \
    --junitxml="$out/payments-controls.xml" \
    tests
