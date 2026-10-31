#!/usr/bin/env python3
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHER = ROOT / "scripts" / "gate_terms.py"
FIXTURE = ROOT / "scripts" / "fixtures" / "gate-terms-canary.sha256"
PATH_LINE = re.compile(r"^[^:\n]+:[0-9]+$")

CASES = (
    ("one.txt", "ZZCANARYONE", True),
    ("two.txt", "  zz   CANARYTWO  ", True),
    ("three.txt", "ZZ  planted--Canary", True),
    ("glue.txt", "zzplantedcanary", False),
    ("short.txt", "zz planted", False),
    ("apart.txt", "xxzz planted canary", False),
)


def fail() -> int:
    print("fail", file=sys.stderr)
    return 1


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, text, _hit in CASES:
            (root / name).write_text(text + "\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(MATCHER), str(FIXTURE), str(root)],
            capture_output=True,
            text=True,
        )
        lines = [ln for ln in proc.stdout.splitlines() if ln]
        if proc.stderr.strip() or any(PATH_LINE.fullmatch(ln) is None for ln in lines):
            return fail()
        expect = {f"{name}:1" for name, _text, hit in CASES if hit}
        if set(lines) != expect or proc.returncode != 1:
            return fail()
        marker = "/" + "Users" + "/"
        gate = (ROOT / "scripts" / "gate.sh").read_text(encoding="utf-8")
        if marker not in gate:
            return fail()
        users = root / "users.txt"
        users.write_text(marker + "x\n", encoding="utf-8")
        grep = subprocess.run(
            ["grep", "-n", "-E", "-i", "--", marker, str(users)],
            capture_output=True,
            text=True,
        )
        if grep.returncode != 0:
            return fail()
        print("users.txt:1")
        for line in sorted(lines):
            print(line)
        return 0


if __name__ == "__main__":
    sys.exit(main())
