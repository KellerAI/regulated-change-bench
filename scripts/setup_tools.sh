#!/bin/sh
# One-time toolchain for running the platform's test suites, the seeder and the baseline runners locally.
#
#   sh scripts/setup_tools.sh            # .tools/venv (pytest) and .tools/junit-console.jar
#   sh scripts/setup_tools.sh --ponens   # also install Ponens 1.22.0 into .tools/ponens-venv (needs git and uv)
#
# Java: a JDK 17 or later; set JAVA_HOME if it is not at /opt/homebrew/opt/openjdk (the ci scripts' default).
set -eu
cd "$(dirname "$0")/.."
mkdir -p .tools

JUNIT_VERSION=1.11.4
JUNIT_SHA256=b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc
JUNIT_URL="https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/$JUNIT_VERSION/junit-platform-console-standalone-$JUNIT_VERSION.jar"

if [ ! -f .tools/junit-console.jar ]; then
  echo "downloading JUnit console launcher $JUNIT_VERSION"
  curl -fsSL -o .tools/junit-console.jar.tmp "$JUNIT_URL"
  got=$(shasum -a 256 .tools/junit-console.jar.tmp | cut -d' ' -f1)
  if [ "$got" != "$JUNIT_SHA256" ]; then
    echo "sha256 mismatch for the JUnit jar: $got" >&2
    rm -f .tools/junit-console.jar.tmp
    exit 1
  fi
  mv .tools/junit-console.jar.tmp .tools/junit-console.jar
fi

if [ ! -x .tools/venv/bin/python ]; then
  python3 -m venv .tools/venv
  .tools/venv/bin/python -m pip install --quiet --upgrade pip
  .tools/venv/bin/python -m pip install --quiet "pytest>=8"
fi
.tools/venv/bin/python -c 'import sys, pytest; assert sys.version_info >= (3, 11), "Python 3.11+ required"; print("pytest", pytest.__version__)'

if [ "${1:-}" = "--ponens" ] && [ ! -x .tools/ponens-venv/bin/ponens ]; then
  PONENS_COMMIT=2f91978
  rm -rf .tools/ponens-clone
  git clone --quiet https://github.com/imandra-ai/ponens .tools/ponens-clone
  git -C .tools/ponens-clone checkout --quiet "$PONENS_COMMIT"
  mkdir -p .tools/ponens-src
  rm -rf .tools/ponens-src/action
  cp -R .tools/ponens-clone/action .tools/ponens-src/action
  uv venv .tools/ponens-venv --python 3.12
  uv pip install --python .tools/ponens-venv/bin/python ".tools/ponens-clone/cli[schema]"
  rm -rf .tools/ponens-clone
  .tools/ponens-venv/bin/ponens --version
fi
echo "tools ready under .tools/"
