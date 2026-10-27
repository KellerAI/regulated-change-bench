#!/usr/bin/env bash
# Runs only the tests tagged "control" and writes JUnit XML reports into <out-dir>.
# Usage: controls.sh <out-dir>   (see junit.sh for environment variables)
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $(basename "$0") <out-dir>" >&2
  exit 64
fi

exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/junit.sh" "$1" --include-tag control
