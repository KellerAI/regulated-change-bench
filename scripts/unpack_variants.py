#!/usr/bin/env python3
"""Turn the published variant bundles into working git checkouts the runners can read.

    python3 scripts/unpack_variants.py [variants/test-seen] [variants/test-heldout] [--force]

Each variant directory holds `records/` and `repo.bundle`. This clones the bundle into `repo/` (the change branch
checked out, `main` as a local branch, no remote left behind). Variants that already have `repo/` are skipped.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"),
       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, env=ENV, capture_output=True)


def unpack(vdir: Path, force: bool) -> bool:
    bundle = vdir / "repo.bundle"
    repo = vdir / "repo"
    if not bundle.is_file():
        return False
    if repo.exists():
        if not force:
            return False
        shutil.rmtree(repo)
    git("clone", "--quiet", str(bundle), str(repo))
    head = subprocess.run(["git", "-C", str(repo), "symbolic-ref", "--short", "HEAD"], check=True, env=ENV,
                          capture_output=True, text=True).stdout.strip()
    if head != "main":
        git("-C", str(repo), "branch", "--quiet", "main", "origin/main")
    git("-C", str(repo), "remote", "remove", "origin")
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("splits", nargs="*", default=[str(ROOT / "variants" / "test-seen"), str(ROOT / "variants" / "test-heldout")])
    ap.add_argument("--force", action="store_true", help="re-clone variants that already have repo/")
    a = ap.parse_args(argv)
    done = skipped = 0
    for split in a.splits:
        for vdir in sorted(Path(split).iterdir()):
            if vdir.is_dir() and vdir.name.startswith("v-"):
                if unpack(vdir, a.force):
                    done += 1
                else:
                    skipped += 1
    print(f"unpacked {done} variants, skipped {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
