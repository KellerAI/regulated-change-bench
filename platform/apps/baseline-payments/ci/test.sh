#!/bin/sh
# Usage: ci/test.sh <out-dir>   Full payments test suite; JUnit XML into <out-dir>.
set -eu
. "$(cd "$(dirname "$0")" && pwd)/env.sh"
out=$(out_dir_arg "$@")
cd "$app_dir"
exec "$PYTHON" -m pytest -q -p no:cacheprovider \
    -o junit_suite_name=payments \
    --junitxml="$out/payments-tests.xml" \
    tests
