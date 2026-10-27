"""Verdict format (design.md §4.6) and writer.

    runs/<arm>/<variant>.json
    {"variant": "v-…", "arm": "…", "decision": "ACCEPT|REJECT|HOLD",
     "obligations": [{"id": "ENC-1", "status": "shown|open|refuted", "note": "…"}],
     "summary": "…", "meta": {"elapsed_s": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0, "error": null, ...}}

Rules applied here, the same for every arm:
- decision and statuses are normalised from common synonyms (APPROVE -> ACCEPT, violated -> refuted, ...);
  "not applicable" entries are dropped (counted in meta.dropped_not_applicable);
- an unparseable output, a missing/unknown decision, or a runner failure gives decision HOLD with meta.error set.
  Scorers must bucket meta.error != null as an error first (design.md: errors count as "not ACCEPT");
- the model's decision is never rewritten to agree with its statuses; a disagreement is flagged in
  meta.inconsistent.
Raw model output goes to runs/<arm>/raw/ (gitignored). Every verdict and raw file is passed through
redact.redact_obj/redact_text first (token-shaped strings and any secret an arm registered are replaced).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .redact import redact_obj, redact_text

DECISIONS = ("ACCEPT", "REJECT", "HOLD")
STATUSES = ("shown", "open", "refuted")
REQUIRED_META = ("elapsed_s", "tokens_in", "tokens_out", "usd", "error")
_SECRETS: set = set()


def register_secret(value: Optional[str]) -> None:
    """Exact strings (tokens, keys) an arm handled; they are redacted from everything saved."""
    if value:
        _SECRETS.add(value)

_DECISION_SYN = {
    "ACCEPT": "ACCEPT", "ACCEPTED": "ACCEPT", "APPROVE": "ACCEPT", "APPROVED": "ACCEPT", "PASS": "ACCEPT",
    "REJECT": "REJECT", "REJECTED": "REJECT", "DENY": "REJECT", "DENIED": "REJECT", "BLOCK": "REJECT", "FAIL": "REJECT",
    "HOLD": "HOLD", "ON HOLD": "HOLD", "DEFER": "HOLD", "NEEDS INFO": "HOLD", "NEEDS MORE INFO": "HOLD",
    "NEEDS MORE INFORMATION": "HOLD", "ESCALATE": "HOLD", "UNKNOWN": "HOLD",
}
_STATUS_SYN = {
    "shown": "shown", "satisfied": "shown", "met": "shown", "pass": "shown", "passed": "shown", "ok": "shown",
    "compliant": "shown", "holds": "shown", "established": "shown", "verified": "shown", "done": "shown",
    "refuted": "refuted", "violated": "refuted", "violation": "refuted", "failed": "refuted", "fail": "refuted",
    "not met": "refuted", "not_met": "refuted", "noncompliant": "refuted", "non-compliant": "refuted",
    "breached": "refuted", "blocked": "refuted",
    "open": "open", "unknown": "open", "unclear": "open", "undetermined": "open", "insufficient evidence": "open",
    "insufficient_evidence": "open", "partial": "open", "pending": "open", "doing": "open", "todo": "open",
    "inconclusive": "open",
}
_NA = {"n/a", "na", "not applicable", "not_applicable", "notapplicable", "out of scope", "out_of_scope", "none"}


def norm_decision(x: Any) -> Optional[str]:
    if not isinstance(x, str):
        return None
    k = re.sub(r"[\s_\-]+", " ", x.strip().upper())
    return _DECISION_SYN.get(k)


def norm_status(x: Any) -> Optional[str]:
    if not isinstance(x, str):
        return None
    k = x.strip().lower()
    if k in _NA:
        return "n/a"
    return _STATUS_SYN.get(k) or _STATUS_SYN.get(k.replace("-", " ").replace("_", " "))


def base_meta(**kw) -> Dict[str, Any]:
    m = {"elapsed_s": 0.0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "error": None}
    m.update(kw)
    return m


def make_verdict(variant: str, arm: str, parsed: Optional[dict], meta: Dict[str, Any],
                 catalog_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    meta = {**base_meta(), **meta}
    obligations: List[Dict[str, str]] = []
    decision = None
    summary = ""
    dropped_na = 0
    unknown_ids: List[str] = []
    if isinstance(parsed, dict):
        decision = norm_decision(parsed.get("decision"))
        summary = str(parsed.get("summary") or "")
        raw_obs = parsed.get("obligations") or []
        if isinstance(raw_obs, dict):  # {"ENC-1": {"status": ...}} or {"ENC-1": "shown"}
            raw_obs = [{"id": k, **(v if isinstance(v, dict) else {"status": v})} for k, v in raw_obs.items()]
        seen = set()
        for o in raw_obs if isinstance(raw_obs, list) else []:
            if not isinstance(o, dict):
                continue
            oid = str(o.get("id") or o.get("obligation") or "").strip()
            st = norm_status(o.get("status"))
            if not oid:
                continue
            if st == "n/a":
                dropped_na += 1
                continue
            if oid in seen:
                continue
            seen.add(oid)
            if catalog_ids and oid not in catalog_ids:
                unknown_ids.append(oid)
            obligations.append({"id": oid, "status": st or "open", "note": str(o.get("note") or o.get("reason") or "")})
        if parsed.get("decision") is not None and decision is None and meta.get("error") is None:
            meta["error"] = f"unknown decision value: {str(parsed.get('decision'))[:60]!r}"
    elif meta.get("error") is None:
        meta["error"] = "unparseable output: no JSON object with a decision"
    if decision is None:
        if meta.get("error") is None:
            meta["error"] = "no decision in output"
        decision = "HOLD"
    sts = {o["status"] for o in obligations}
    meta["inconsistent"] = bool((decision == "ACCEPT" and (sts - {"shown"})) or
                                (decision == "REJECT" and "refuted" not in sts and obligations) or
                                (decision == "HOLD" and "refuted" in sts))
    if dropped_na:
        meta["dropped_not_applicable"] = dropped_na
    if unknown_ids:
        meta["ids_not_in_catalog"] = unknown_ids
    return {"variant": variant, "arm": arm, "decision": decision, "obligations": obligations, "summary": summary,
            "meta": meta}


def error_verdict(variant: str, arm: str, error: str, **meta) -> Dict[str, Any]:
    return make_verdict(variant, arm, None, {**meta, "error": error})


def validate(v: Dict[str, Any]) -> List[str]:
    probs = []
    for k in ("variant", "arm", "decision", "obligations", "summary", "meta"):
        if k not in v:
            probs.append(f"missing {k}")
    if v.get("decision") not in DECISIONS:
        probs.append(f"bad decision {v.get('decision')!r}")
    for o in v.get("obligations") or []:
        if o.get("status") not in STATUSES:
            probs.append(f"bad status {o}")
    for k in REQUIRED_META:
        if k not in (v.get("meta") or {}):
            probs.append(f"meta missing {k}")
    return probs


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def verdict_path(runs_dir: Path, arm: str, variant: str) -> Path:
    return Path(runs_dir) / arm / f"{variant}.json"


def write_verdict(runs_dir: Path, verdict: Dict[str, Any]) -> Path:
    probs = validate(verdict)
    if probs:
        raise ValueError(f"invalid verdict: {probs}")
    verdict = redact_obj(verdict, _SECRETS)
    p = verdict_path(runs_dir, verdict["arm"], verdict["variant"])
    _atomic_write(p, json.dumps(verdict, indent=2, ensure_ascii=False) + "\n")
    return p


def save_raw(runs_dir: Path, arm: str, variant: str, name: str, content) -> Path:
    p = Path(runs_dir) / arm / "raw" / f"{variant}.{name}"
    if isinstance(content, (dict, list)):
        content = json.dumps(redact_obj(content, _SECRETS), indent=2, ensure_ascii=False)
    _atomic_write(p, redact_text(content if isinstance(content, str) else str(content), _SECRETS))
    return p
