"""Shared pieces for packs: the Family record, PR text, and helpers for common record perturbations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .. import people
from ..builder import VariantBuilder, iso

HW = "apps/baseline-mortgage/src/main/java/mortgage/"
HWT = "apps/baseline-mortgage/src/test/java/"
LL = "apps/baseline-payments/payments/"
LLT = "apps/baseline-payments/tests/"


@dataclass
class Family:
    name: str
    app: str
    apply: Callable[[VariantBuilder, str], None]
    modes: tuple = ("defect", "clean")
    after_prior: Callable[[VariantBuilder, str], None] | None = None
    author_role: str | None = None   # e.g. "change_approver" when the family needs an author who could approve


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def describe(b: VariantBuilder, summary: str, details: list[str], testing: str | None = None) -> str:
    """PR description in the house style, shared by every mode so prose can't give the label away."""
    lines = [summary, "", "Changes:"] + [f"- {d}" for d in details]
    lines += ["", "Testing:", f"- {testing or 'Unit tests updated; full suite green locally.'}"]
    if b.rng.random() < 0.3:
        lines += ["", "Rollout: standard release train."]
    return "\n".join(lines)


def other_engineer(b: VariantBuilder) -> str:
    return b.rng.choice([p for p in people.engineers(b.app) if p != b.author])


def approver_for(b: VariantBuilder) -> str:
    return b.rng.choice([p for p in people.with_role("change_approver", b.app) if p != b.author])


def set_approval_commit(b: VariantBuilder, kind: str, commit: str):
    for a in b.records["approvals"]:
        if a["kind"] == kind:
            a["commit"] = commit


def approval_before_last_commit(b: VariantBuilder, kind: str, commit: str):
    """Approval names `commit` and is timestamped between that commit and the next one."""
    idx = next(i for i, c in enumerate(b.records["change"]["commits"]) if c["sha"] == commit)
    t0 = ts(b.records["change"]["commits"][idx]["at"])
    t1 = ts(b.records["change"]["commits"][idx + 1]["at"]) if idx + 1 < len(b.records["change"]["commits"]) else b.as_of
    at = t0 + (t1 - t0) / 2
    for a in b.records["approvals"]:
        if a["kind"] == kind:
            a["commit"] = commit
            a["at"] = iso(at)


def add_exception(b: VariantBuilder, obligation: str, component: str, *, days_left: int, scope: str,
                  approver: str | None = None, requester: str | None = None, compensating: str | None = "",
                  status: str = "approved") -> dict:
    requester = requester or b.author
    approver = approver or b.rng.choice(people.with_role("risk_owner"))
    e = {"id": f"EXC-0{b.rng.randint(180, 260)}", "obligation": obligation, "component": component, "scope": scope,
         "status": status, "requested_by": people.primary_email(requester),
         "approved_by": people.primary_email(approver) if approver else None,
         "approved_at": iso(b.as_of - timedelta(days=b.rng.randint(20, 120))),
         "expires": (b.as_of + timedelta(days=days_left)).date().isoformat(),
         "compensating_control": compensating if compensating != "" else
         b.rng.choice(["Access restricted to the internal network segment; reviewed weekly by security operations",
                       "Daily reconciliation report reviewed by the payments operations lead",
                       "Manual second review recorded in the change ticket for every use"])}
    b.records["exceptions"].append(e)
    return e
