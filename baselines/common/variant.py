"""Load one bench variant (design.md §4.3).

    v-<id>/
      repo/      git repo: main history + the change branch (base..head)
      records/   change.json, tickets.json, approvals.json, directory.json, exceptions.json, ledger.json,
                 ci/ (JUnit XML + run.json), evidence/, as_of.json

The loader is deliberately tolerant about record field names: the seeder's exact schema is its own business, so
base/head are looked up under a few spellings, and every record file is carried verbatim into the packet.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_KEYS = ("base", "base_sha", "base_commit", "base_ref")
HEAD_KEYS = ("head", "head_sha", "head_commit", "head_ref")


class VariantError(RuntimeError):
    pass


def _git_env() -> Dict[str, str]:
    import os
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_COUNT": "0", "GIT_PAGER": "cat", "PAGER": "cat"})
    return env


# Every git call on a variant neutralises repo-local config that could execute something (the variant's
# .git/config is untrusted input): no fsmonitor, hooks, pager or external diff/textconv.
_SAFE = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.pager=cat",
         "-c", "diff.external=", "-c", "core.sshCommand=false"]


@dataclass
class Variant:
    root: Path
    id: str
    repo: Path
    records: Path
    change: Dict[str, Any] = field(default_factory=dict)
    base: str = ""
    head: str = ""

    # ------------------------------------------------------------------ git
    def git(self, *args: str, check: bool = True, binary: bool = False):
        r = subprocess.run(["git", "-C", str(self.repo), *_SAFE, *args], capture_output=True, env=_git_env(),
                           timeout=120)
        if check and r.returncode != 0:
            raise VariantError(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace').strip()[:400]}")
        return r.stdout if binary else r.stdout.decode("utf-8", errors="replace")

    def rev(self, ref: str) -> str:
        return self.git("rev-parse", "--verify", f"{ref}^{{commit}}").strip()

    def show(self, ref: str, path: str) -> Optional[bytes]:
        r = subprocess.run(["git", "-C", str(self.repo), *_SAFE, "show", "--no-textconv", f"{ref}:{path}"],
                           capture_output=True,
                           env=_git_env(), timeout=60)
        return r.stdout if r.returncode == 0 else None

    def show_text(self, ref: str, path: str) -> Optional[str]:
        b = self.show(ref, path)
        if b is None:
            return None
        if b"\x00" in b[:8192]:
            return None
        return b.decode("utf-8", errors="replace")

    def ls_tree(self, ref: str, prefix: str = "") -> List[str]:
        args = ["ls-tree", "-r", "--name-only", ref]
        if prefix:
            args += ["--", prefix]
        return [p for p in self.git(*args).splitlines() if p]

    def export(self, commit: str, dest: Path) -> List[str]:
        """Write the tree of `commit` into `dest` by reading blobs (`git ls-tree -r -z` + `git cat-file --batch`),
        never through `git archive` or a checkout, so no in-tree attributes or repo config can run a filter
        driver. Symlinks (mode 120000) and submodules (160000) are skipped; paths with `..`, an absolute path or a
        `.git` component are refused. Returns the skipped paths."""
        listing = self.git("ls-tree", "-r", "-z", "--full-tree", commit, binary=True)
        entries, skipped = [], []
        for rec in listing.split(b"\x00"):
            if not rec:
                continue
            meta, _, path_b = rec.partition(b"\t")
            mode, otype, sha = meta.decode().split()
            path = path_b.decode("utf-8", errors="surrogateescape")
            parts = Path(path).parts
            if path.startswith("/") or ".." in parts or ".git" in parts:
                raise VariantError(f"refusing tree path {path!r}")
            if otype != "blob" or mode == "120000":
                skipped.append(path)
                continue
            entries.append((mode, sha, path))
        if not entries:
            return skipped
        p = subprocess.Popen(["git", "-C", str(self.repo), *_SAFE, "cat-file", "--batch"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, env=_git_env())
        assert p.stdin is not None and p.stdout is not None
        dest = Path(dest)
        for mode, sha, path in entries:
            p.stdin.write(sha.encode() + b"\n")
            p.stdin.flush()
            header = p.stdout.readline().split()
            if len(header) != 3 or header[1] != b"blob":
                p.kill()
                raise VariantError(f"cat-file: unexpected header {header!r} for {path}")
            size = int(header[2])
            data = p.stdout.read(size)
            p.stdout.read(1)  # trailing newline
            out = dest / path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            out.chmod(0o755 if mode == "100755" else 0o644)
        p.stdin.close()
        p.wait(timeout=60)
        return skipped

    def changed_files(self) -> List[Tuple[str, str]]:
        """[(status, path)] for base..head; renames reported as R with the new path."""
        out = self.git("diff", "--no-ext-diff", "--no-textconv", "--name-status", "--find-renames", self.base,
                       self.head)
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if not parts or not parts[0]:
                continue
            st = parts[0][0]
            path = parts[-1]
            rows.append((st, path))
        return rows

    def diff(self, context: int = 3) -> str:
        return self.git("diff", "--no-ext-diff", "--no-textconv", f"-U{context}", "--find-renames", "--no-color",
                        self.base, self.head)

    def diffstat(self) -> str:
        return self.git("diff", "--no-ext-diff", "--no-textconv", "--stat=200", "--find-renames", "--no-color",
                        self.base, self.head)

    def commits(self) -> List[Dict[str, str]]:
        fmt = "%H%x1f%an%x1f%ae%x1f%ad%x1f%cn%x1f%ce%x1f%B%x1e"
        out = self.git("log", "--reverse", "--date=iso-strict", f"--format={fmt}", f"{self.base}..{self.head}")
        rows = []
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if not rec.strip():
                continue
            f = rec.split("\x1f")
            if len(f) < 7:
                continue
            rows.append({"sha": f[0], "author": f[1], "author_email": f[2], "date": f[3], "committer": f[4],
                         "committer_email": f[5], "message": f[6].strip()})
        return rows

    # ------------------------------------------------------------------ records
    def record_files(self) -> List[Path]:
        if not self.records.is_dir():
            return []
        return sorted(p for p in self.records.rglob("*") if p.is_file() and not p.name.startswith("."))

    def record_json(self, name: str) -> Any:
        p = self.records / name
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text())
        except ValueError:
            return None

    def as_of(self) -> Any:
        return self.record_json("as_of.json")


def _pick(d: Dict[str, Any], keys) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):  # {"sha": ...} / {"ref": ...}
            for kk in ("sha", "commit", "ref"):
                if isinstance(v.get(kk), str) and v[kk].strip():
                    return v[kk].strip()
    return None


def load_variant(path) -> Variant:
    root = Path(path).resolve()
    repo = root / "repo"
    records = root / "records"
    if not (repo / ".git").exists() and not (repo / "HEAD").exists():
        raise VariantError(f"{root}: no git repo at repo/")
    v = Variant(root=root, id=root.name, repo=repo, records=records)
    v.change = v.record_json("change.json") or {}
    base = _pick(v.change, BASE_KEYS)
    head = _pick(v.change, HEAD_KEYS)
    if not head:
        head = "HEAD"
    if not base:
        # fall back to the merge-base with main (or master)
        for main in ("main", "master"):
            r = subprocess.run(["git", "-C", str(repo), *_SAFE, "merge-base", main, head], capture_output=True,
                               text=True, env=_git_env())
            if r.returncode == 0 and r.stdout.strip():
                base = r.stdout.strip()
                break
    if not base:
        raise VariantError(f"{root}: cannot determine the change's base commit")
    v.base = v.rev(base)
    v.head = v.rev(head)
    return v


def find_variants(paths: List[str], variants_dir: Optional[str]) -> List[Path]:
    out: List[Path] = [Path(p).resolve() for p in paths or []]
    if variants_dir:
        d = Path(variants_dir).resolve()
        out += sorted(p for p in d.iterdir() if p.is_dir() and p.name.startswith("v-") and (p / "repo").exists())
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq
