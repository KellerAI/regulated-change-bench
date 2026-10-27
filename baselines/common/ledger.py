"""The cloud-spend ledger: runs/cost-ledger.jsonl, one JSON object per paid run.

    {"ts": "2026-10-23T20:01:02Z", "arm": "opus-packet", "variant": "v-…", "usd": 0.21, "basis": "…"}

`basis` says how the number was obtained (Bedrock token counts x list price, CLI-reported list-price equivalent, ...).
KB_LEDGER overrides the path (remote workers write their own and remote/mbp.sh merges it back). The cap is
$500 across the ledger; `spent()` sums it and `check_cap()` refuses a run that would cross it.
"""

from __future__ import annotations

import datetime as _dt
import fcntl
import json
import os
from pathlib import Path
from typing import Optional

from . import RUNS

LEDGER = Path(os.environ["KB_LEDGER"]) if os.environ.get("KB_LEDGER") else RUNS / "cost-ledger.jsonl"
CAP_USD = 500.0


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(arm: str, variant: str, usd: float, basis: str, path: Optional[Path] = None) -> dict:
    p = Path(path or LEDGER)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": now_utc(), "arm": arm, "variant": variant, "usd": round(float(usd), 4), "basis": basis}
    with open(p, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(row) + "\n")
        fcntl.flock(f, fcntl.LOCK_UN)
    return row


def spent(path: Optional[Path] = None) -> float:
    p = Path(path or LEDGER)
    if not p.exists():
        return 0.0
    total = 0.0
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            total += float(json.loads(line).get("usd") or 0)
        except (ValueError, TypeError):
            continue
    return total


def check_cap(next_max_usd: float, path: Optional[Path] = None) -> None:
    s = spent(path)
    if s + next_max_usd > CAP_USD:
        raise RuntimeError(f"cost cap: ledger ${s:.2f} + this run's ceiling ${next_max_usd:.2f} > ${CAP_USD:.0f}")
