#!/bin/sh
# Usage: ci/run-controls.sh <app> <out-dir>   Control tests only, JUnit XML into <out-dir>.
set -eu
app=$1
out=$2
root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$out"
# bash, not sh: the mortgage scripts use pipefail, which dash (Ubuntu's /bin/sh) lacks.
exec bash "$root/apps/$app/ci/controls.sh" "$out"
