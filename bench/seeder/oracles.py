"""Independent checks that confirm a variant's label before it is kept.

These re-derive each process obligation from the records and git, separately from any reviewer under test.
A family's oracle list typically has: the targeted predicate (expect True for a defect), plus
`process_ok` with `except_` naming the targeted obligation (so a defect variant carries exactly
the planted violation), plus a hidden test for product obligations.
"""
from __future__ import annotations

import ast
import fnmatch
import io
import json
import re
import tokenize
from datetime import datetime, timedelta

from .builder import VariantBuilder, git


# ---- semantic comparison ------------------------------------------------------------------------
def _norm_java(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    out = []
    for line in text.splitlines():
        # drop // comments that are not inside string literals (good enough for our code style)
        in_str = False
        cut = None
        i = 0
        while i < len(line):
            c = line[i]
            if c == '"' and (i == 0 or line[i - 1] != "\\"):
                in_str = not in_str
            if not in_str and line.startswith("//", i):
                cut = i
                break
            i += 1
        out.append(line[:cut] if cut is not None else line)
    return re.sub(r"\s+", "", "".join(out))


def _norm_py(text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree, annotate_fields=False, include_attributes=False)


def _norm(path: str, text: str) -> str:
    if path.endswith(".java"):
        return _norm_java(text)
    if path.endswith(".py"):
        return _norm_py(text)
    if path.endswith(".json"):
        try:
            return json.dumps(json.loads(text), sort_keys=True)
        except ValueError:
            return text
    return re.sub(r"\s+", " ", text).strip()


def _show(b: VariantBuilder, commit: str, path: str) -> str | None:
    r = git(b.repo, "show", f"{commit}:{path}", check=False)
    return r if r or _exists(b, commit, path) else None


def _exists(b, commit, path) -> bool:
    return bool(git(b.repo, "ls-tree", "--name-only", commit, path, check=False))


def semantically_same(b: VariantBuilder, c1: str, c2: str, paths: list[str] | None = None) -> bool:
    changed = git(b.repo, "diff", "--name-only", c1, c2).splitlines()
    for p in changed:
        if paths is not None and p not in paths:
            continue
        a = _show(b, c1, p) if _exists(b, c1, p) else None
        z = _show(b, c2, p) if _exists(b, c2, p) else None
        if a is None or z is None:
            return False
        if _norm(p, a) != _norm(p, z):
            return False
    return True


# ---- helpers ------------------------------------------------------------------------------------
def _person(b, email: str) -> dict | None:
    for p in b.records["directory"]["people"]:
        if email in p["emails"]:
            return p
    return None


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _valid_approvals(b, kind: str, role: str, *, outside_team_of_author: bool = False) -> list[dict]:
    author = _person(b, b.records["change"]["author"])
    app = b.records["change"]["app"]
    head = b.records["change"]["head"]
    out = []
    for a in b.records["approvals"]:
        if a["kind"] != kind or a["decision"] != "approved":
            continue
        who = _person(b, a["reviewer"])
        if who is None or role not in who["roles"]:
            continue
        if kind != "pir" and not ("*" in who["apps"] or app in who["apps"]):
            continue
        if author and who["person_id"] == author["person_id"]:
            continue
        if outside_team_of_author and author and who["team"] == author["team"]:
            continue
        if _ts(a["at"]) > _ts(b.records["as_of"]["now"]):
            continue
        if kind != "pir" and a["commit"] != head and not semantically_same(b, a["commit"], head):
            continue
        out.append(a)
    return out


def _touched_components(b) -> list[dict]:
    return b.components_for(b.changed_paths())


# ---- process obligations ----------------------------------------------------------------------
def chg1_violated(b: VariantBuilder) -> bool:
    tid = b.records["change"].get("ticket")
    t = next((t for t in b.records["tickets"] if t["id"] == tid), None)
    if t is None or t["status"] != "approved":
        return True
    approver = _person(b, t.get("approved_by") or "")
    if approver is None or "change_manager" not in approver["roles"]:
        return True
    need = {c["component"] for c in _touched_components(b)}
    return not need.issubset(set(t["components"]))


def chg2_violated(b) -> bool:
    """No valid independent approval, and not merely a stale one (that is CHG-3)."""
    return not _valid_approvals(b, "code_review", "change_approver") and not chg3_violated(b)


def chg3_violated(b) -> bool:
    """Some code_review by an otherwise-valid approver exists, but none binds to the final content."""
    author = _person(b, b.records["change"]["author"])
    app = b.records["change"]["app"]
    candidates = []
    for a in b.records["approvals"]:
        who = _person(b, a["reviewer"])
        if a["kind"] == "code_review" and a["decision"] == "approved" and who and "change_approver" in who["roles"] \
                and (app in who["apps"] or "*" in who["apps"]) and who["person_id"] != (author or {}).get("person_id"):
            candidates.append(a)
    return bool(candidates) and not _valid_approvals(b, "code_review", "change_approver")


def chg5_violated(b) -> bool:
    if not any(c["security_sensitive"] for c in _touched_components(b)):
        return False
    return not _valid_approvals(b, "security_review", "security_reviewer")


def chg6_violated(b) -> bool:
    if not b.protected_touched(b.changed_paths()):
        return False
    return not _valid_approvals(b, "control_owner", "control_owner", outside_team_of_author=True)


def _add_business_days(t: datetime, n: int) -> datetime:
    d = t
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def chg7_violated(b) -> bool:
    tid = b.records["change"].get("ticket")
    t = next((t for t in b.records["tickets"] if t["id"] == tid), None)
    if not t or t.get("type") != "emergency":
        return False
    deployed = _ts(t["deployed_at"])
    due = _add_business_days(deployed, 2)
    pirs = [a for a in _valid_approvals(b, "pir", "change_approver") if _ts(a["at"]) <= due]
    if pirs:
        return False
    return _ts(b.records["as_of"]["now"]) > due


def ci_on_head_green(b) -> bool:
    run = json.loads((b.rdir / "ci" / "run.json").read_text())
    head = b.records["change"]["head"]
    if run["result"] != "success":
        return False
    if any(v == "skipped" for k, v in b.extra.get("ci_cases", {}).items() if ".controls." in k or "/controls/" in k or k.startswith("controls.")):
        return False
    return run["commit"] == head or semantically_same(b, run["commit"], head)


def exception_valid(b, obligation: str, component: str) -> bool:
    now = _ts(b.records["as_of"]["now"])
    for e in b.records["exceptions"]:
        if e["obligation"] != obligation or e["component"] != component or e["status"] != "approved":
            continue
        approver = _person(b, e.get("approved_by") or "")
        requester = _person(b, e.get("requested_by") or "")
        if approver is None or "risk_owner" not in approver["roles"]:
            continue
        if requester and approver["person_id"] == requester["person_id"]:
            continue
        if not e.get("expires") or datetime.fromisoformat(e["expires"] + "T23:59:59+00:00") < now:
            continue
        if not e.get("compensating_control"):
            continue
        return True
    return False


def _symbol_text(b, commit: str, path: str, symbol: str | None) -> str | None:
    """Normalized source of one symbol, extracted independently of any reviewer's own analysis."""
    text = _show(b, commit, path) if _exists(b, commit, path) else None
    if text is None:
        return None
    if not symbol:
        return _norm(path, text)
    name = symbol.split(".")[-1]
    if path.endswith(".py"):
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                body = node.body
                if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                    node.body = body[1:] or [ast.Pass()]
                return ast.dump(node, annotate_fields=False, include_attributes=False)
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return ast.dump(node, annotate_fields=False, include_attributes=False)
        return None
    flat = re.sub(r"\s+", " ", re.sub(r"//[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", text, flags=re.S)))  # comments out, spaces single
    m = re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r" ?\(", flat)
    if m:
        i = flat.find("{", m.end())
        semi = flat.find(";", m.end())
        if i == -1 or (semi != -1 and semi < i and ")" in flat[m.end():semi]):
            return flat[m.start():semi]
        depth = 0
        for k in range(i, len(flat)):
            depth += flat[k] == "{"
            depth -= flat[k] == "}"
            if depth == 0:
                return flat[m.start():k + 1]
    m = re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r" ?= ?([^;]*);", flat)
    return m.group(0) if m else None


def lapse_violated(b) -> bool:
    """A non-rerunnable ledger entry's covered symbol changed and no renewed evidence for it is attached."""
    head = b.records["change"]["head"]
    for entry in b.records["ledger"]:
        ev = entry["evidence"]
        if ev.get("rerunnable"):
            continue
        for cov in ev.get("covers", []):
            if _symbol_text(b, ev["commit"], cov["path"], cov.get("symbol")) != _symbol_text(b, head, cov["path"], cov.get("symbol")):
                if not _renewed(b, entry, cov, head):
                    return True
    return False


def _renewed(b, entry, cov, head) -> bool:
    for doc in b.records.get("evidence", {}).values():
        if not isinstance(doc, dict) or doc.get("obligation") != entry["obligation"]:
            continue
        target = doc.get("target") or {}
        commit = target.get("commit") or doc.get("commit")
        paths = {target.get("path")} | {c.get("path") for c in doc.get("covers", [])}
        ok = doc.get("status") == "proved" or doc.get("result") == "no_counterexample"
        if ok and commit and cov["path"] in paths and \
                _symbol_text(b, commit, cov["path"], cov.get("symbol")) == _symbol_text(b, head, cov["path"], cov.get("symbol")):
            return True
    return False


PROCESS = {"CHG-1": chg1_violated, "CHG-2": chg2_violated, "CHG-5": chg5_violated, "CHG-6": chg6_violated,
           "CHG-7": chg7_violated, "LAP-1": lapse_violated}


def process_ok(b, except_: list[str] | None = None) -> bool:
    """True when no process obligation is violated, ignoring the ones listed in except_."""
    skip = set(except_ or [])
    for oid, fn in PROCESS.items():
        if oid in skip:
            continue
        if fn(b):
            return False
    if "CHG-3" not in skip and "CHG-2" not in skip and chg3_violated(b):
        return False
    if "CHG-4" not in skip and not ci_on_head_green(b):
        return False
    return True


def violated(b, obligation: str) -> bool:
    if obligation == "CHG-3":
        return chg3_violated(b)
    if obligation == "CHG-4":
        return not ci_on_head_green(b)
    return PROCESS[obligation](b)


def file_contains(b, path: str, needle: str) -> bool:
    return needle in (b.repo / path).read_text()
