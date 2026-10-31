#!/usr/bin/env python3
import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path

MAX_N = 3

EXCLUDE_DIRS = {".git", ".tools", "repo", "__pycache__"}
EXCLUDE_FILES = {
    "gate.sh",
    "CODEOWNERS",
    "gate-terms.sha256",
    "gate-terms-canary.sha256",
}
TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
HASH_LINE = re.compile(r"[0-9a-f]{64}")
FIXED_SKIP = re.compile(r'grep -vF "([^"]*)"')

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent


def tokens(text: str) -> tuple[str, ...]:
    folded = unicodedata.normalize("NFKC", text).lower()
    return tuple(part for part in TOKEN_SPLIT.split(folded) if part)


def digest(parts: tuple[str, ...]) -> str:
    return hashlib.sha256(" ".join(parts).encode()).hexdigest()


def line_hit(parts: tuple[str, ...], hashes: set[str]) -> bool:
    limit = min(MAX_N, len(parts))
    for size in range(1, limit + 1):
        stop = len(parts) - size + 1
        for start in range(stop):
            if digest(parts[start : start + size]) in hashes:
                return True
    return False


def load_hashes(path: Path) -> set[str]:
    hashes: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if HASH_LINE.fullmatch(line) is None:
            print("invalid hash file", file=sys.stderr)
            raise SystemExit(2)
        hashes.add(line)
    return hashes


def fixed_skips(repo: Path) -> tuple[str, ...]:
    gate = repo / "scripts" / "gate.sh"
    if not gate.is_file():
        return ()
    text = gate.read_text(encoding="utf-8", errors="replace")
    return tuple(item for item in FIXED_SKIP.findall(text) if item)


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDE_DIRS]
        for name in filenames:
            if name in EXCLUDE_FILES:
                continue
            yield Path(dirpath) / name


def scan(root: Path, hashes: set[str], skips: tuple[str, ...]) -> int:
    hits = 0
    for path in iter_files(root):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if any(skip in line for skip in skips):
                continue
            parts = tokens(line)
            if parts and line_hit(parts, hashes):
                print(f"{rel}:{lineno}")
                hits += 1
    return hits


def main() -> int:
    hash_path = Path(sys.argv[1]) if len(sys.argv) > 1 else SCRIPT_DIR / "gate-terms.sha256"
    root = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO
    hashes = load_hashes(hash_path)
    skips = fixed_skips(REPO)
    return 1 if scan(root, hashes, skips) else 0


if __name__ == "__main__":
    sys.exit(main())
