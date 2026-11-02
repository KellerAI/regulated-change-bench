#!/bin/sh
# Publication checks print locations only; private matching rules stay outside this tree.
set -eu
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" scripts/gate_terms.py
