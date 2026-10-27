# Shared setup for the payments CI scripts. Sourced, not executed.
#
# PYTHON selects the interpreter (Python 3.11+ with pytest). When unset, the
# nearest .tools/venv above the app is used, falling back to python3.

app_dir=$(cd "$(dirname "$0")/.." && pwd)

find_python() {
    dir=$app_dir
    while [ "$dir" != "/" ]; do
        if [ -x "$dir/.tools/venv/bin/python" ]; then
            echo "$dir/.tools/venv/bin/python"
            return 0
        fi
        dir=$(dirname "$dir")
    done
    echo python3
}

PYTHON=${PYTHON:-$(find_python)}

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    echo "payments: $PYTHON is not Python 3.11 or newer (set PYTHON)" >&2
    exit 2
fi
if ! "$PYTHON" -c 'import pytest' 2>/dev/null; then
    echo "payments: pytest is not installed for $PYTHON" >&2
    exit 2
fi

out_dir_arg() {
    if [ "$#" -ne 1 ] || [ -z "$1" ]; then
        echo "usage: $(basename "$0") <out-dir>" >&2
        exit 2
    fi
    mkdir -p "$1"
    cd "$1" && pwd
}

export PYTHONDONTWRITEBYTECODE=1
