#!/usr/bin/env python3
import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path

MAX_N = 3
EXCLUDE_DIRS = {".git", ".tools", "__pycache__"}
TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
HASH_LINE = re.compile(r"[0-9a-f]{64}")
PUBLIC_HANDLES = re.compile(r"@[a-z0-9_-]+(?:/[a-z0-9_-]+)?", re.I)
PUBLIC_REFERENCE = "kellerai.io/resources/benchmarking-regulated-change-review"
USER_PATH = re.compile("/" + "Users" + "/", re.I)
SECRETS = re.compile(
    r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|aws_(?:account|profile)|"
    r"arn:" r"aws|[0-9]{12}:inference-profile|sk-[A-Za-z0-9_-]{16,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_" r"pat_|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY|eyJ[A-Za-z0-9_-]{8,}\."
    r"[A-Za-z0-9_-]{8,}\."
)
# Existing redaction and fake-credential fixtures intentionally contain token shapes.
# Scope these exceptions to their exact paths, not every file with the same basename.
SECRET_FIXTURES = {
    "baselines/common/redact.py",
    "baselines/common/bedrock.py",
    "baselines/tests/test_cli_plumbing.py",
    "baselines/tests/fakes/claude",
}

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


def load_hashes(path: Path, root: Path) -> set[str]:
    path = path.resolve()
    if path.is_relative_to(root.resolve()) or path.is_relative_to(REPO.resolve()):
        raise ValueError("private rule file must be outside the repository")
    hashes: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if HASH_LINE.fullmatch(line) is None:
            raise ValueError("invalid private rule file")
        hashes.add(line)
    if not hashes:
        raise ValueError("empty private rule file")
    return hashes


def iter_files(root: Path):
    def unreadable(_error):
        raise OSError("unreadable scan directory")

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=unreadable):
        rel = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDE_DIRS
                            and not (name == "repo" and len(rel.parts) == 3
                                     and rel.parts[0] == "variants"))
        if any((Path(dirpath) / name).is_symlink() for name in dirnames):
            raise OSError("symlink scan directory")
        for name in filenames:
            yield Path(dirpath) / name


def scan(root: Path, hashes: set[str]) -> int:
    hits = 0
    for path in iter_files(root):
        if path.is_symlink():
            raise OSError("symlink scan file")
        data = path.read_bytes()
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            # GitHub handles in the ownership declaration are deliberately public.
            name_line = PUBLIC_HANDLES.sub("", line) if rel == ".github/CODEOWNERS" else line
            # Exempt this published reference, never unrelated text on the same line.
            name_line = name_line.replace(PUBLIC_REFERENCE, "")
            private_hit = bool(hashes) and line_hit(tokens(name_line), hashes)
            public_hit = USER_PATH.search(line) or (rel not in SECRET_FIXTURES and SECRETS.search(line))
            if private_hit or public_hit:
                print(f"{rel}:{lineno}")
                hits += 1
    return hits


def main() -> int:
    if len(sys.argv) > 3:
        print("usage: gate_terms.py [PRIVATE_RULE_FILE [ROOT]]", file=sys.stderr)
        return 2
    rule_file = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GATE_TERMS_FILE")
    root = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else REPO
    try:
        if not root.is_dir():
            raise ValueError("scan root must be a directory")
        hashes = load_hashes(Path(rule_file), root) if rule_file else set()
        if not rule_file:
            print("private name scan not configured; checking public path and credential patterns only")
        hits = scan(root, hashes)
    except (OSError, UnicodeError, ValueError):
        print("publication check failed: unreadable tree or invalid private rule file", file=sys.stderr)
        return 2
    if not hits:
        print("configured publication checks passed")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
