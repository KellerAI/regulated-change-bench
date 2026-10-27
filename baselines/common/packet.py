"""The review packet for the no-tool arms (design.md §5): everything a reviewer needs, as one Markdown document.

Sections, in order:
  1. the bank's obligation catalog        controls/obligations.json at the BASE commit (the approved version)
  2. the change-management policy         controls/change-policy.md at base
  3. the rest of the bank's controls area controls/* at base (components, protected paths, registry, params, ...)
  4. the change: its commits              base..head, author, date, full message
  5. the diff                             git diff --stat and the unified diff base..head
  6. changed files                        full text of every changed file at head
  7. change-management records            every file under records/ except the CI run, verbatim
  8. CI summary                           records/ci: run.json and a digest of every JUnit XML file

The packet carries no variant directory name, label, or anything not in the variant itself. The token count is an
estimate (characters / 3.6, calibrated against Ollama's prompt_eval_count on the fixtures; see baselines/README.md).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .variant import Variant

CATALOG = "controls/obligations.json"
POLICY = "controls/change-policy.md"
CONTROLS_DIR = "controls/"
MAX_FILE_CHARS = 150_000
MAX_RECORD_CHARS = 120_000
MAX_TESTCASES_LISTED = 600
CHARS_PER_TOKEN = 3.6

LANG = {".py": "python", ".java": "java", ".json": "json", ".md": "markdown", ".sh": "bash", ".xml": "xml",
        ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".txt": "text", ".sql": "sql", ".mcl": "modelcheck"}


def estimate_tokens(text: str) -> int:
    return int(math.ceil(len(text) / CHARS_PER_TOKEN))


def fence(text: str, lang: str = "") -> str:
    longest = max((len(m) for m in re.findall(r"`{3,}", text)), default=2)
    f = "`" * max(3, longest + 1)
    if not text.endswith("\n"):
        text += "\n"
    return f"{f}{lang}\n{text}{f}\n"


def _lang(path: str) -> str:
    return LANG.get(Path(path).suffix.lower(), "")


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated: {len(text) - limit} more characters not shown ...]\n"


def _pretty_json(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except ValueError:
        return raw


@dataclass
class Packet:
    text: str
    sections: List[Tuple[str, int]] = field(default_factory=list)  # (title, est tokens)
    tokens_est: int = 0
    sha256: str = ""
    catalog_ids: List[str] = field(default_factory=list)
    catalog_ref: str = ""

    def manifest(self) -> Dict:
        return {"tokens_est": self.tokens_est, "chars": len(self.text), "sha256": self.sha256,
                "sections": [{"title": t, "tokens_est": n} for t, n in self.sections],
                "catalog_ref": self.catalog_ref, "catalog_ids": self.catalog_ids}


def catalog_ids_from(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        doc = json.loads(raw)
    except ValueError:
        return []
    items = doc.get("obligations") if isinstance(doc, dict) else doc
    if isinstance(items, dict):
        return [str(k) for k in items.keys()]
    ids = []
    for it in items or []:
        if isinstance(it, dict) and it.get("id"):
            ids.append(str(it["id"]))
    return ids


def load_catalog(v: Variant) -> Tuple[Optional[str], str]:
    """(raw catalog text, where it came from). Base first: the approved catalog, whatever the change does to it."""
    for ref, label in ((v.base, "base"), (v.head, "head")):
        raw = v.show_text(ref, CATALOG)
        if raw is not None:
            return raw, f"{label} {ref[:12]}"
    return None, "missing"


# ------------------------------------------------------------------ JUnit digest

def junit_digest(path: Path) -> Tuple[str, Dict[str, int]]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        return f"(could not parse {path.name}: {e})\n", {}
    cases = list(root.iter("testcase"))
    counts = {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0}
    by_class: Dict[str, List[str]] = {}
    problems: List[str] = []
    for c in cases:
        cls = c.get("classname") or ""
        name = c.get("name") or "?"
        mark = "pass"
        for tag, key, word in (("failure", "failures", "FAIL"), ("error", "errors", "ERROR"),
                               ("skipped", "skipped", "SKIP")):
            el = c.find(tag)
            if el is not None:
                counts[key] += 1
                mark = word
                msg = (el.get("message") or (el.text or "")).strip().replace("\n", " ")
                if tag != "skipped" or msg:
                    problems.append(f"- {word} {cls}#{name}: {msg[:400]}")
                break
        by_class.setdefault(cls, []).append(name if mark == "pass" else f"{name} [{mark}]")
    suite_attrs = []
    for s in [root] + list(root.iter("testsuite")):
        if s.tag in ("testsuite", "testsuites"):
            a = {k: s.get(k) for k in ("name", "tests", "failures", "errors", "skipped", "time", "timestamp",
                                       "hostname") if s.get(k) is not None}
            if a:
                suite_attrs.append(f"{s.tag} " + ", ".join(f"{k}={v}" for k, v in a.items()))
    lines = [f"File `{path.name}`: {counts['tests']} test cases, {counts['failures']} failures, "
             f"{counts['errors']} errors, {counts['skipped']} skipped."]
    if suite_attrs:
        lines.append("Suites: " + "; ".join(suite_attrs[:12]) + (" ..." if len(suite_attrs) > 12 else ""))
    if problems:
        lines.append("Failures, errors and skips:")
        lines += problems[:200]
    if len(cases) <= MAX_TESTCASES_LISTED:
        lines.append("Test cases by class:")
        for cls in sorted(by_class):
            lines.append(f"- {cls or '(no class)'}: " + ", ".join(by_class[cls]))
    else:
        lines.append(f"({len(cases)} test cases; only failures, errors and skips are listed.)")
    return "\n".join(lines) + "\n", counts


# ------------------------------------------------------------------ builder

def build_packet(v: Variant) -> Packet:
    parts: List[Tuple[str, str]] = []
    change_id = v.change.get("id") or v.change.get("change_id") or "(no id)"
    title = v.change.get("title") or ""

    header = (f"# Review packet: change {change_id}" + (f" — {title}" if title else "") + "\n\n"
              f"Repository change under review: base `{v.base}` .. head `{v.head}`.\n")
    parts.append(("Header", header))

    # 1. catalog
    raw, where = load_catalog(v)
    ids = catalog_ids_from(raw)
    s = f"## 1. Obligation catalog (`{CATALOG}` at {where})\n\n"
    s += fence(_pretty_json(raw), "json") if raw is not None else "(The repository has no obligation catalog.)\n"
    parts.append(("Obligation catalog", s))

    # 2. change policy
    pol = v.show_text(v.base, POLICY)
    s = f"## 2. Change-management policy (`{POLICY}` at base {v.base[:12]})\n\n"
    s += fence(pol, "markdown") if pol is not None else "(No change-management policy file at base.)\n"
    parts.append(("Change policy", s))

    # 3. rest of controls/
    others = [p for p in v.ls_tree(v.base, CONTROLS_DIR) if p not in (CATALOG, POLICY)]
    s = f"## 3. The bank's other controls files (`{CONTROLS_DIR}` at base {v.base[:12]})\n\n"
    if not others:
        s += "(none)\n"
    for p in others:
        t = v.show_text(v.base, p)
        if t is None:
            s += f"### `{p}`\n\n(binary file, not shown)\n\n"
            continue
        if p.endswith(".json"):
            t = _pretty_json(t)
        s += f"### `{p}`\n\n" + fence(_cap(t, MAX_FILE_CHARS), _lang(p)) + "\n"
    parts.append(("Other controls", s))

    # 4. commits
    commits = v.commits()
    s = f"## 4. Commits on the change ({len(commits)})\n\n"
    for c in commits:
        s += (f"### {c['sha']}\n\n- author: {c['author']} <{c['author_email']}>\n- date: {c['date']}\n"
              f"- committer: {c['committer']} <{c['committer_email']}>\n\n" + fence(c["message"] or "(empty)", "text")
              + "\n")
    parts.append(("Commits", s))

    # 5. diff
    s = "## 5. Diff base..head\n\n" + fence(v.diffstat() or "(empty)", "text") + "\n" + fence(v.diff() or "(empty)", "diff")
    parts.append(("Diff", s))

    # 6. changed files at head
    changed = v.changed_files()
    s = f"## 6. Changed files at head ({len(changed)})\n\n"
    for st, p in changed:
        if st == "D":
            s += f"### `{p}` (deleted)\n\n"
            continue
        t = v.show_text(v.head, p)
        if t is None:
            s += f"### `{p}` (binary, not shown)\n\n"
            continue
        s += f"### `{p}`\n\n" + fence(_cap(t, MAX_FILE_CHARS), _lang(p)) + "\n"
    parts.append(("Changed files", s))

    # 7. records (except the CI run)
    s = "## 7. Change-management records (`records/`)\n\n"
    ci_dir = v.records / "ci"
    for f in v.record_files():
        rel = f.relative_to(v.records).as_posix()
        if f.is_relative_to(ci_dir):
            continue
        try:
            t = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            s += f"### `records/{rel}` (binary, not shown)\n\n"
            continue
        if f.suffix == ".json":
            t = _pretty_json(t)
        s += f"### `records/{rel}`\n\n" + fence(_cap(t, MAX_RECORD_CHARS), _lang(rel)) + "\n"
    parts.append(("Records", s))

    # 8. CI summary
    s = "## 8. CI summary (`records/ci/`: the change's own CI run)\n\n"
    if not ci_dir.is_dir():
        s += "(No CI run was recorded for this change.)\n"
    else:
        for f in sorted(p for p in ci_dir.rglob("*") if p.is_file() and not p.name.startswith(".")):
            rel = f.relative_to(v.records).as_posix()
            if f.suffix.lower() == ".xml":
                digest, _ = junit_digest(f)
                s += f"### `records/{rel}` (JUnit XML, digested)\n\n" + digest + "\n"
            else:
                try:
                    t = f.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    s += f"### `records/{rel}` (binary, not shown)\n\n"
                    continue
                if f.suffix == ".json":
                    t = _pretty_json(t)
                s += f"### `records/{rel}`\n\n" + fence(_cap(t, MAX_RECORD_CHARS), _lang(rel)) + "\n"
    parts.append(("CI summary", s))

    text = "\n".join(body for _, body in parts)
    return Packet(text=text, sections=[(t, estimate_tokens(b)) for t, b in parts], tokens_est=estimate_tokens(text),
                  sha256=hashlib.sha256(text.encode()).hexdigest(), catalog_ids=ids, catalog_ref=where)


def main(argv=None) -> int:
    """python -m baselines.common.packet <variant-dir> [--out FILE]: print the packet's manifest (and write it)."""
    import argparse
    from .variant import load_variant
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("variant")
    ap.add_argument("--out", help="write the packet Markdown here")
    a = ap.parse_args(argv)
    pk = build_packet(load_variant(a.variant))
    if a.out:
        Path(a.out).write_text(pk.text)
    print(json.dumps(pk.manifest(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
