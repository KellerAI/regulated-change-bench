#!/usr/bin/env python3
"""Build the hand-made fixture variants used to test the baseline runners (not part of the bench).

    python3 baselines/fixtures/build.py [--python PY]

Creates baselines/fixtures/v-q7m2ka/ and baselines/fixtures/v-h3tz9p/ (gitignored; rebuilt on demand) in the
design.md §4.3 layout. Both share one tiny payments repo (src/base) and one change (src/change: a read-only
payment-status route on an existing action). They differ only in the change's code_review approval (see README.md for the expected
decisions). Commits use fixed authors and dates, so the SHAs are reproducible. The change's own CI run is real:
pytest runs at head with PY (default: the bench venv's python) and its JUnit XML is normalised (no timestamps,
hostnames or durations) into records/ci/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_BASE = HERE / "src" / "base"
SRC_CHANGE = HERE / "src" / "change"
REPO_ROOT = HERE.parent.parent
DEFAULT_PY = Path(os.environ.get("KAB_PYTHON", REPO_ROOT / ".tools" / "venv" / "bin" / "python"))

PEOPLE = {
    "priya": ("Priya Nair", "priya.nair@fernbrook.example"),
    "tomas": ("Tomas Ortega", "tomas.ortega@fernbrook.example"),
}

DIRECTORY = {"people": [
    {"name": "Priya Nair", "email": "priya.nair@fernbrook.example", "aliases": ["pnair@fernbrook.example"],
     "team": "payments-eng", "roles": ["engineer", "code_approver"]},
    {"name": "Tomas Ortega", "email": "tomas.ortega@fernbrook.example", "aliases": ["tortega@fernbrook.example"],
     "team": "payments-eng", "roles": ["engineer", "code_approver"]},
    {"name": "Dana Whitfield", "email": "dana.whitfield@fernbrook.example", "aliases": [],
     "team": "it-security", "roles": ["security_reviewer"]},
    {"name": "Marcus Lee", "email": "marcus.lee@fernbrook.example", "aliases": ["mlee@fernbrook.example"],
     "team": "change-management", "roles": ["change_manager"]},
    {"name": "Ana Souza", "email": "ana.souza@fernbrook.example", "aliases": [],
     "team": "it-controls", "roles": ["control_owner"]},
]}

FIXTURES = {
    # code reviewer, the only difference between the two
    "v-q7m2ka": "pnair@fernbrook.example",
    "v-h3tz9p": "tomas.ortega@fernbrook.example",
}


def run(cmd, cwd=None, env=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"{' '.join(map(str, cmd))} failed:\n{r.stdout}\n{r.stderr}")
    return r


def git_env(who: str, date: str) -> dict:
    name, email = PEOPLE[who]
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/tmp"),
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": date,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": date}
    return env


def commit(repo: Path, who: str, date: str, message: str) -> str:
    env = git_env(who, date)
    run(["git", "add", "-A"], cwd=repo, env=env)
    run(["git", "commit", "-q", "--no-gpg-sign", "-m", message], cwd=repo, env=env)
    return run(["git", "rev-parse", "HEAD"], cwd=repo, env=env).stdout.strip()


def copy_tree(src: Path, dst: Path, skip_top=()):
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if rel.parts and rel.parts[0] in skip_top:
            continue
        t = dst / rel
        if p.is_dir():
            t.mkdir(parents=True, exist_ok=True)
        else:
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, t)
            if p.suffix == ".sh":
                t.chmod(0o755)


def normalise_junit(path: Path) -> None:
    x = path.read_text()
    x = re.sub(r'timestamp="[^"]*"', 'timestamp="2026-10-19T16:31:00"', x)
    x = re.sub(r'hostname="[^"]*"', 'hostname="ci-runner-2"', x)
    x = re.sub(r'time="[^"]*"', 'time="0.010"', x)
    path.write_text(x)


def build(vid: str, reviewer: str, py: Path) -> None:
    out = HERE / vid
    if out.exists():
        shutil.rmtree(out)
    repo = out / "repo"
    repo.mkdir(parents=True)
    env = git_env("tomas", "2026-09-01T10:00:00Z")
    run(["git", "init", "-q", "-b", "main"], cwd=repo, env=env)
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    copy_tree(SRC_BASE, repo, skip_top=("docs",))
    c1 = commit(repo, "tomas", "2026-09-01T10:00:00Z", "Initial import of the payments service")
    copy_tree(SRC_BASE / "docs", repo / "docs")
    c2 = commit(repo, "priya", "2026-09-20T14:05:00Z", "Document the payments API")
    run(["git", "checkout", "-q", "-b", "chg/payment-status"], cwd=repo, env=env)
    copy_tree(SRC_CHANGE, repo)
    c3 = commit(repo, "priya", "2026-10-19T16:20:00Z",
                "Add payment status endpoint\n\nRead-only status lookup for operations staff, served by the existing "
                "view_account action.\nNo new permissions.")

    rec = out / "records"
    (rec / "ci").mkdir(parents=True)
    (rec / "evidence").mkdir()
    w = lambda name, obj: (rec / name).write_text(json.dumps(obj, indent=2) + "\n")
    w("change.json", {
        "id": "CHG-2026-0412", "title": "Expose payment status endpoint",
        "description": "Adds GET /payments/{id}/status so operations staff can look up a payment's state. "
                       "Read-only; served by the existing view_account action; no new permissions.",
        "author": "priya.nair@fernbrook.example", "base": c2, "head": c3, "branch": "chg/payment-status",
        "commits": [c3], "emergency": False, "ticket": "PAY-1187"})
    w("tickets.json", {"tickets": [
        {"id": "PAY-1187", "title": "Payment status lookup for operations", "status": "approved",
         "components": ["payments.routes", "payments.tests", "docs"],
         "approver": "marcus.lee@fernbrook.example", "approved_at": "2026-10-14T09:12:00Z"},
        {"id": "PAY-1179", "title": "Payments API documentation", "status": "closed", "components": ["docs"],
         "approver": "marcus.lee@fernbrook.example", "approved_at": "2026-09-18T11:00:00Z"}]})
    w("approvals.json", {"approvals": [
        {"kind": "code_review", "by": reviewer, "commit": c3, "state": "approved", "at": "2026-10-19T17:02:00Z"},
        {"kind": "security_review", "by": "dana.whitfield@fernbrook.example", "commit": c3, "state": "approved",
         "at": "2026-10-20T09:40:00Z"}]})
    w("directory.json", DIRECTORY)
    w("exceptions.json", {"exceptions": []})
    w("ledger.json", {"records": [
        {"change": "CHG-2026-0377", "commit": c2, "accepted_by": "marcus.lee@fernbrook.example",
         "accepted_at": "2026-09-21T10:00:00Z", "obligations": [
             {"obligation": "MFA-1", "evidence": {"kind": "control_test",
              "ref": "tests/controls/test_routes_control.py::test_privileged_routes_require_mfa", "commit": c2,
              "covers": ["apps/baseline-payments/payments/routes.py"], "coverage": "exhaustive", "result": "passed"}}]}]})
    w("as_of.json", {"as_of": "2026-10-20T15:00:00Z"})

    # the change's own CI run, at head
    ci_tmp = out / "ci-tmp"
    ci_tmp.mkdir()
    cienv = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHON": str(py), "PYTHONDONTWRITEBYTECODE": "1"}
    results = {}
    for script in ("run-tests.sh", "run-controls.sh"):
        r = run(["sh", f"ci/{script}", "baseline-payments", str(ci_tmp)], cwd=repo, env=cienv, check=False)
        results[script] = r.returncode
    for x in sorted(ci_tmp.glob("*.xml")):
        normalise_junit(x)
        shutil.move(str(x), rec / "ci" / x.name)
    shutil.rmtree(ci_tmp)
    w("ci/run.json", {"commit": c3, "executor": "ci-runner-2", "pipeline": "pr-checks",
                      "started_at": "2026-10-19T16:30:12Z", "finished_at": "2026-10-19T16:31:05Z",
                      "steps": [{"name": "ci/run-tests.sh baseline-payments", "exit_code": results["run-tests.sh"]},
                                {"name": "ci/run-controls.sh baseline-payments", "exit_code": results["run-controls.sh"]}]})
    status = run(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    if status:
        raise SystemExit(f"{vid}: CI run left the worktree dirty:\n{status}")
    print(f"{vid}: base {c2[:12]} head {c3[:12]} ci {results} reviewer {reviewer}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python", default=str(DEFAULT_PY), help="python with pytest, for the fixture's CI run")
    a = ap.parse_args()
    for vid, reviewer in FIXTURES.items():
        build(vid, reviewer, Path(a.python))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
