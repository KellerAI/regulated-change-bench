"""Shared driver loop for the arm runners: pick variants, skip finished ones, time each review, write the verdict.

An arm supplies `review(variant_dir, ctx) -> ReviewResult`; the driver turns that into a verdict file. Any exception
becomes an error verdict (decision HOLD, meta.error set), so one bad variant never stops a batch.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import RUNS, ledger
from .jsonx import extract_json
from .variant import find_variants
from .verdict import error_verdict, make_verdict, save_raw, verdict_path, write_verdict


class StopBatch(Exception):
    """Raised by an arm when continuing is pointless or harmful (usage limit, lost login, cost cap). No verdict is
    written for the current variant, so a later run picks it up again."""


@dataclass
class ReviewResult:
    text: Optional[str]                         # the model's final answer text (parsed for the verdict JSON)
    meta: Dict[str, Any] = field(default_factory=dict)
    parsed: Optional[dict] = None               # set when the arm already has the object (e.g. a verdict file)
    raw: Dict[str, Any] = field(default_factory=dict)   # name -> content, saved under runs/<arm>/raw/
    catalog_ids: Optional[List[str]] = None
    decision_override: Optional[dict] = None    # arms that compute the verdict themselves (ponens) pass it whole


def add_common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--variant", action="append", default=[], help="variant directory (repeatable)")
    ap.add_argument("--variants-dir", help="run every v-* directory in here")
    ap.add_argument("--runs-dir", default=str(RUNS), help="where runs/<arm>/<variant>.json go (default: repo runs/)")
    ap.add_argument("--arm", help="arm name override")
    ap.add_argument("--force", action="store_true", help="re-run variants that already have a verdict")
    ap.add_argument("--limit", type=int, default=0, help="stop after N reviews (0 = all)")
    ap.add_argument("--max-usd", type=float, default=None,
                    help="paid arms: stop the batch before a variant whose ceiling estimate would take the "
                         "cost ledger (runs/cost-ledger.jsonl) past this total; the $500 cap always applies")


def drive(args, arm: str, review: Callable[[Path], ReviewResult],
          estimate: Optional[Callable[[Path], float]] = None) -> int:
    """`estimate(variant_dir)` is a paid arm's per-variant USD ceiling; with it, every variant is checked against
    --max-usd and the ledger cap before it starts, and the batch stops (exit 75) instead of crossing either."""
    runs = Path(args.runs_dir)
    variants = find_variants(args.variant, args.variants_dir)
    if not variants:
        print("no variants given (--variant DIR or --variants-dir DIR)", file=sys.stderr)
        return 2
    done = 0
    worst = 0
    for vdir in variants:
        vid = vdir.name
        out = verdict_path(runs, arm, vid)
        if out.exists() and not args.force:
            print(f"[{arm}] {vid}: verdict exists, skipping (--force to redo)")
            continue
        if estimate is not None:
            ceiling = float(estimate(vdir))
            spent = ledger.spent()
            limit = min(ledger.CAP_USD, args.max_usd if args.max_usd is not None else ledger.CAP_USD)
            if spent + ceiling > limit:
                print(f"[{arm}] {vid}: stopping the batch: ledger ${spent:.2f} + ceiling ${ceiling:.2f} > "
                      f"limit ${limit:.2f}", file=sys.stderr)
                return 75
        t0 = time.time()
        try:
            res = review(vdir)
            elapsed = round(time.time() - t0, 2)
            for name, content in (res.raw or {}).items():
                save_raw(runs, arm, vid, name, content)
            if res.decision_override is not None:
                o = res.decision_override
                v = make_verdict(vid, arm, o, {"elapsed_s": elapsed, **res.meta, **(o.get("meta") or {})},
                                 res.catalog_ids)
            else:
                parsed, how = (res.parsed, "provided") if res.parsed is not None else extract_json(res.text)
                meta = {"elapsed_s": elapsed, **res.meta, "parse": how}
                meta.setdefault("elapsed_s", elapsed)
                v = make_verdict(vid, arm, parsed, meta, res.catalog_ids)
        except StopBatch as e:
            print(f"[{arm}] {vid}: stopping the batch: {e}", file=sys.stderr)
            return 75
        except Exception as e:  # noqa: BLE001 - one variant's failure must not stop the batch
            elapsed = round(time.time() - t0, 2)
            tb = traceback.format_exc()
            save_raw(runs, arm, vid, "error.txt", tb)
            v = error_verdict(vid, arm, f"{type(e).__name__}: {e}"[:500], elapsed_s=elapsed)
            worst = 1
        p = write_verdict(runs, v)
        m = v["meta"]
        print(f"[{arm}] {vid}: {v['decision']} ({len(v['obligations'])} obligations) "
              f"{m.get('elapsed_s')}s in={m.get('tokens_in')} out={m.get('tokens_out')} usd={m.get('usd')} "
              f"error={m.get('error')} -> {p}")
        done += 1
        if args.limit and done >= args.limit:
            break
    return worst
