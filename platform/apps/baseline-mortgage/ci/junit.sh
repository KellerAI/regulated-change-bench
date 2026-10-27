#!/usr/bin/env bash
# Compiles the app and its tests, then runs them with the JUnit Platform console launcher.
# Shared by test.sh and controls.sh.
#
# Usage: junit.sh <out-dir> [extra console launcher options...]
#
# Environment:
#   JAVA_HOME    JDK 17 or later (default /opt/homebrew/opt/openjdk)
#   JUNIT_JAR    junit-platform-console-standalone jar
#                (default <repo>/.tools/junit-console.jar, repo located relative to this script)
#   CONTROLS_DIR policy files read by the control tests (default <platform>/controls/mortgage)
#   JAVA_OPTS    extra JVM options for the test run
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $(basename "$0") <out-dir> [launcher options...]" >&2
  exit 64
fi

OUT_DIR="$1"
shift

CI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$CI_DIR/.." && pwd)"
PLATFORM_DIR="$(cd "$APP_DIR/../.." && pwd)"
REPO_DIR="$(cd "$PLATFORM_DIR/.." && pwd)"

JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk}"
JUNIT_JAR="${JUNIT_JAR:-$REPO_DIR/.tools/junit-console.jar}"
CONTROLS_DIR="${CONTROLS_DIR:-$PLATFORM_DIR/controls/mortgage}"
JAVA_OPTS="${JAVA_OPTS:-}"

if [ ! -x "$JAVA_HOME/bin/javac" ]; then
  echo "javac not found under JAVA_HOME=$JAVA_HOME" >&2
  exit 2
fi
if [ ! -f "$JUNIT_JAR" ]; then
  echo "JUnit console jar not found at $JUNIT_JAR; set JUNIT_JAR" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mortgage-build.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT

# Writes a single failing JUnit report so a broken build shows up as a failure, not as no results.
report_compile_failure() {
  local stage="$1"
  local log="$2"
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo "<testsuite name=\"mortgage-compile\" tests=\"1\" failures=\"1\" errors=\"0\" skipped=\"0\">"
    echo "  <testcase classname=\"mortgage.Build\" name=\"compile-$stage\">"
    echo "    <failure message=\"javac failed ($stage)\"><![CDATA["
    sed 's/]]>/]] >/g' "$log"
    echo "]]></failure>"
    echo "  </testcase>"
    echo "</testsuite>"
  } > "$OUT_DIR/TEST-mortgage-compile.xml"
}

compile() {
  local stage="$1"
  local source_root="$2"
  local classpath="$3"
  local sources="$BUILD_DIR/$stage-sources.txt"
  local options=(--release 17 -encoding UTF-8 -d "$BUILD_DIR/$stage")
  if [ -n "$classpath" ]; then
    options+=(-cp "$classpath")
  fi
  find "$source_root" -name '*.java' | sort | sed 's/.*/"&"/' > "$sources"
  if ! "$JAVA_HOME/bin/javac" "${options[@]}" @"$sources" > "$BUILD_DIR/$stage-javac.log" 2>&1; then
    cat "$BUILD_DIR/$stage-javac.log" >&2
    report_compile_failure "$stage" "$BUILD_DIR/$stage-javac.log"
    exit 1
  fi
}

compile main "$APP_DIR/src/main/java" ""
compile test "$APP_DIR/src/test/java" "$BUILD_DIR/main:$JUNIT_JAR"

# shellcheck disable=SC2086
"$JAVA_HOME/bin/java" $JAVA_OPTS \
  -Dmortgage.controls.dir="$CONTROLS_DIR" \
  -jar "$JUNIT_JAR" execute \
  --disable-banner \
  --disable-ansi-colors \
  --details="${JUNIT_DETAILS:-summary}" \
  --class-path "$BUILD_DIR/main:$BUILD_DIR/test" \
  --scan-class-path "$BUILD_DIR/test" \
  --reports-dir "$OUT_DIR" \
  --fail-if-no-tests \
  "$@"
