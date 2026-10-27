#!/bin/sh
# Usage: ci/run-tests.sh <app> <out-dir>   Full test suite for one app, JUnit XML into <out-dir>.
set -eu
app=$1
out=$2
root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$out"
exec sh "$root/apps/$app/ci/test.sh" "$out"
