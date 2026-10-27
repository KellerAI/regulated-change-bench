"""Build one benchmark variant: a git repo with history plus change-management records.

Families (bench/seeder/packs/*/) drive a VariantBuilder:

    b.edit(path, old, new)            anchored edit, `old` must occur exactly once
    b.write(path, text) / b.delete(path)
    b.commit(message)                 commit on the change branch as the PR author
    b.records                         dict of records, filled by b.default_records()
    b.label(...)                      the sealed answer for this variant
    b.oracle(...)                     hidden check that confirms the label

Nothing a family writes into the repo or records may reveal the label.
"""
from __future__ import annotations

import fnmatch
import json
import os
import random
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import people

UTC = timezone.utc
MAIN_HISTORY = [
    # (message, author id, iso time, mutation of the tree before commit)
    ("Import Fernbrook platform 3.4", "p-bot", "2026-08-31T14:00:00+00:00", None),
    ("Docs: describe the pipeline report columns", "p-tortega", "2026-09-14T15:20:00+00:00", "docs_pipeline"),
    ("Docs: payee directory field notes", "p-jweiss", "2026-09-29T18:05:00+00:00", "docs_payees"),
]


class SeedError(Exception):
    """A family could not apply to this tree; the generator skips the attempt."""


def git(repo: Path, *args: str, env: dict | None = None, check: bool = True) -> str:
    e = dict(os.environ)
    e.update({"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"})
    if env:
        e.update(env)
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=e)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Label:
    mode: str                      # "clean" | "defect"
    obligations: list[str]         # violated obligations (empty when clean)
    severity: str = "critical"     # critical | high | medium
    note: str = ""                 # one line for the report


@dataclass
class VariantBuilder:
    platform: Path                 # the platform/ tree to import
    out: Path                      # variant directory to create
    rng: random.Random
    app: str                       # "baseline-mortgage" | "baseline-payments"
    family: str
    pack: str
    author: str = ""               # person id, chosen in __post_init__
    records: dict = field(default_factory=dict)
    commits: list[dict] = field(default_factory=list)
    label_: Label | None = None
    oracles: list[dict] = field(default_factory=list)
    ci_commit: str | None = None   # where the PR's CI ran; default head
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        self.repo = self.out / "repo"
        self.rdir = self.out / "records"
        self.as_of = self._pick_as_of()
        self.author = self.author or self.rng.choice(people.engineers(self.app))
        self._clock = self.as_of - timedelta(days=self.rng.randint(2, 6), hours=self.rng.randint(0, 5))
        self._build_main()
        git(self.repo, "checkout", "-q", "-b", self._branch_name())
        self.base = git(self.repo, "rev-parse", "main")

    # ---- time -------------------------------------------------------------------------------
    def _pick_as_of(self) -> datetime:
        day = datetime(2026, 10, 5, tzinfo=UTC) + timedelta(days=self.rng.randint(0, 25))
        while day.weekday() >= 5:
            day += timedelta(days=1)
        return day.replace(hour=self.rng.randint(14, 21), minute=self.rng.randint(0, 59))

    def tick(self, minutes_lo: int = 20, minutes_hi: int = 300) -> datetime:
        self._clock += timedelta(minutes=self.rng.randint(minutes_lo, minutes_hi))
        if self._clock >= self.as_of:
            self._clock = self.as_of - timedelta(minutes=self.rng.randint(5, 30))
        return self._clock

    # ---- repo -------------------------------------------------------------------------------
    def _branch_name(self) -> str:
        return f"{people.BY_ID[self.author]['aliases'][0].split('.')[-1].split('-')[0]}/change-{self.rng.randint(100, 999)}"

    def _build_main(self):
        shutil.copytree(self.platform, self.repo, ignore=shutil.ignore_patterns("build", "out", "__pycache__", ".pytest_cache"))
        git(self.repo, "init", "-q", "-b", "main")
        for message, who, when, mutation in MAIN_HISTORY:
            if mutation:
                self._main_mutation(mutation)
            self._commit_as(message, who, datetime.fromisoformat(when))

    def _main_mutation(self, name: str):
        docs = self.repo / "docs"
        docs.mkdir(exist_ok=True)
        if name == "docs_pipeline":
            (docs / "pipeline-report.md").write_text(
                "# Pipeline report\n\nColumns: case id, stage, assigned role, days in stage, requested amount (rounded).\n"
                "The report never includes applicant identifiers.\n")
        elif name == "docs_payees":
            (docs / "payee-directory.md").write_text(
                "# Payee directory\n\nPayees are keyed by an internal id. Account numbers are stored sealed and shown masked.\n")

    def _commit_as(self, message: str, who: str, when: datetime) -> str:
        email = people.primary_email(who)
        name = people.BY_ID[who]["name"]
        env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": iso(when),
               "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": iso(when)}
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", message, env=env)
        return git(self.repo, "rev-parse", "HEAD")

    def path(self, rel: str) -> Path:
        return self.repo / rel

    def read(self, rel: str) -> str:
        return self.path(rel).read_text()

    def write(self, rel: str, text: str):
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def delete(self, rel: str):
        self.path(rel).unlink()

    def edit(self, rel: str, old: str, new: str, count: int = 1):
        text = self.read(rel)
        n = text.count(old)
        if n != count:
            raise SeedError(f"{rel}: anchor occurs {n} times, expected {count}: {old[:80]!r}")
        self.write(rel, text.replace(old, new))

    def has(self, rel: str, needle: str) -> bool:
        p = self.path(rel)
        return p.exists() and needle in p.read_text()

    def commit(self, message: str, who: str | None = None) -> str:
        when = self.tick()
        sha = self._commit_as(message, who or self.author, when)
        self.commits.append({"sha": sha, "message": message, "author": people.primary_email(who or self.author),
                             "at": iso(when)})
        return sha

    @property
    def head(self) -> str:
        return git(self.repo, "rev-parse", "HEAD")

    def changed_paths(self, a: str | None = None, b: str | None = None) -> list[str]:
        out = git(self.repo, "diff", "--name-only", a or self.base, b or "HEAD")
        return [p for p in out.splitlines() if p]

    # ---- controls lookups ---------------------------------------------------------------------
    def controls_json(self, rel: str) -> dict:
        return json.loads((self.repo / "controls" / rel).read_text())

    def components_for(self, paths: list[str]) -> list[dict]:
        found = {}
        for app in ("mortgage", "baseline-payments"):
            f = self.repo / "controls" / app / "components.json"
            if not f.exists():
                continue
            table = json.loads(f.read_text())
            entries = table.get("components", table) if isinstance(table, dict) else table
            items = entries.items() if isinstance(entries, dict) else ((e["glob"], e) for e in entries)
            for glob, info in items:
                for p in paths:
                    if fnmatch.fnmatch(p, glob):
                        found[info["component"]] = bool(info.get("security_sensitive"))
        return [{"component": c, "security_sensitive": s} for c, s in sorted(found.items())]

    def protected_touched(self, paths: list[str]) -> bool:
        globs = json.loads((self.repo / "controls" / "protected-paths.json").read_text())["protected"]
        return any(fnmatch.fnmatch(p, g) for p in paths for g in globs)

    # ---- records ----------------------------------------------------------------------------
    def default_records(self, title: str, description: str, *, emergency: bool = False) -> dict:
        """Records for a well-run change: approved ticket, independent reviews on head, CI on head."""
        app = self.app
        head = self.head
        paths = self.changed_paths()
        comps = self.components_for(paths)
        approver = self.rng.choice([p for p in people.with_role("change_approver", app) if p != self.author])
        manager = self.rng.choice(people.with_role("change_manager"))
        ticket_id = f"CHG-{self.rng.randint(24000, 26999)}"
        first_at = datetime.fromisoformat(self.commits[0]["at"].replace("Z", "+00:00"))
        last_at = datetime.fromisoformat(self.commits[-1]["at"].replace("Z", "+00:00"))
        approvals = [self._approval(approver, "code_review", head, last_at)]
        if any(c["security_sensitive"] for c in comps):
            approvals.append(self._approval(self.rng.choice(people.with_role("security_reviewer")), "security_review", head, last_at))
        if self.protected_touched(paths):
            approvals.append(self._approval(self.rng.choice(people.with_role("control_owner")), "control_owner", head, last_at))
        pr = f"PR-{self.rng.randint(1200, 1999)}"
        self.records = {
            "change": {
                "id": pr, "title": title, "description": description, "app": app,
                "author": people.primary_email(self.author), "branch": git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"),
                "base": self.base, "head": head, "commits": self.commits, "emergency": emergency, "ticket": ticket_id,
                "opened_at": self.commits[0]["at"],
            },
            "tickets": [{
                "id": ticket_id, "type": "emergency" if emergency else "standard", "status": "approved",
                "summary": title, "components": [c["component"] for c in comps],
                "requested_by": people.primary_email(self.author), "approved_by": people.primary_email(manager),
                "approved_at": iso(first_at - timedelta(hours=self.rng.randint(4, 72))),
                "risk": "medium" if any(c["security_sensitive"] for c in comps) else "low",
            }],
            "approvals": approvals,
            "directory": people.directory(),
            "exceptions": base_exceptions(self.as_of),
            "ledger": [],          # filled by the generator from the pack's prior-acceptance table
            "evidence": {},        # path under records/evidence -> json
            "as_of": {"now": iso(self.as_of), "timezone": "America/New_York",
                      "business_days": "Monday to Friday; no holidays in this period"},
        }
        return self.records

    def _approval(self, who: str, kind: str, commit: str, after: datetime) -> dict:
        at = after + timedelta(minutes=self.rng.randint(15, 600))
        if at >= self.as_of:
            at = self.as_of - timedelta(minutes=self.rng.randint(2, 10))
        return {"reviewer": people.primary_email(who), "kind": kind, "decision": "approved", "commit": commit, "at": iso(at)}

    def approval(self, kind: str) -> dict:
        for a in self.records["approvals"]:
            if a["kind"] == kind:
                return a
        raise SeedError(f"no {kind} approval")

    # ---- answer ------------------------------------------------------------------------------
    def label(self, mode: str, obligations: list[str] | None = None, severity: str = "critical", note: str = ""):
        self.label_ = Label(mode, obligations or [], severity, note)

    def oracle(self, kind: str, **spec):
        """kind: 'hidden_test' (run files against head, expect pass/fail) or 'predicate' (name + args)."""
        self.oracles.append({"kind": kind, **spec})

    # ---- output ------------------------------------------------------------------------------
    def write_records(self):
        self.rdir.mkdir(parents=True, exist_ok=True)
        for name in ("change", "tickets", "approvals", "directory", "exceptions", "ledger", "as_of"):
            (self.rdir / f"{name}.json").write_text(json.dumps(self.records[name], indent=2) + "\n")
        for rel, doc in self.records.get("evidence", {}).items():
            p = self.rdir / "evidence" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(doc, indent=2) + "\n" if not isinstance(doc, str) else doc)


def base_exceptions(as_of: datetime) -> list[dict]:
    """Background register present in every variant: some active, some expired, none about the change."""
    d = lambda days: (as_of + timedelta(days=days)).date().isoformat()
    return [
        {"id": "EXC-0141", "obligation": "SES-1", "component": "payments.session",
         "scope": "Batch reconciliation service account sessions", "status": "approved",
         "requested_by": people.primary_email("p-mcosta"), "approved_by": people.primary_email("p-hvasquez"),
         "approved_at": d(-210), "expires": d(-30),
         "compensating_control": "Service account restricted to reconciliation endpoints; activity reviewed weekly"},
        {"id": "EXC-0167", "obligation": "LOG-1", "component": "mortgage.logging",
         "scope": "Legacy import job writes masked last-4 of bank account number", "status": "approved",
         "requested_by": people.primary_email("p-wli"), "approved_by": people.primary_email("p-ohaddad"),
         "approved_at": d(-95), "expires": d(80),
         "compensating_control": "Import logs retained 30 days in restricted bucket"},
        {"id": "EXC-0172", "obligation": "MFA-1", "component": "mortgage.routes",
         "scope": "Read-only health route used by the load balancer", "status": "withdrawn",
         "requested_by": people.primary_email("p-dfarrell"), "approved_by": None,
         "approved_at": None, "expires": None, "compensating_control": None},
    ]
