#!/usr/bin/env python3
"""Regenerate RESULTS.md and reports/results.json from the published verdicts and keys.

    python3 scripts/results.py            # rewrite RESULTS.md and reports/results.json
    python3 scripts/results.py --check    # regenerate to memory and fail if the committed files differ
    python3 scripts/results.py --runs-dir runs-mine --extra-arm gpt-oss-120b "gpt-oss-120b (my rerun)"
                                          # score a replication from another directory (runs-mine/<split>/<arm>/);
                                          # writes runs-mine/RESULTS.md and runs-mine/results.json, never the published files

Everything is recounted from runs/<split>/<arm>/v-*.json against bench/key/<split>.json; nothing is copied from
earlier reports. Scoring rules are in bench/score/score.py (ACCEPT on a defective variant is a false all-clear;
a missing or unparseable verdict counts as "not ACCEPT" and is reported as an error).

bench/key/disputed.json lists seen-split clean labels disputed since v1.1 (CORRECTIONS.md). The keys are not edited;
the original seen tables are unchanged and one extra table excludes the disputed changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench.score.score import load_verdicts, score  # noqa: E402

SPLITS = ["test-seen", "test-heldout"]
# Fixed presentation order (by kind of reviewer, not by score): packet arms, tool-using arm, CI gate in both modes.
ARMS = [
    ("opus-packet", "Claude Opus 5.5, packet (no tools)"),
    ("gpt-oss-120b", "gpt-oss-120b, packet (local)"),
    ("qwen3.8-27b", "Qwen 3.8 27B, packet (local)"),
    ("grok-cli", "Grok 4.7 via Cursor agent, packet (ask mode)"),
    ("claude-code", "Claude Code with tools (Opus 5.5)"),
    ("ponens-no-trace", "Ponens CI action, no trace (default)"),
    ("ponens-agent-trace", "Ponens goal resolution, post-hoc trace (gpt-oss-120b)"),
]
COST = {
    "opus-packet": "Bedrock list price", "claude-code": "Bedrock list price",
    "grok-cli": "plan quota", "gpt-oss-120b": "$0 API, local compute", "qwen3.8-27b": "$0 API, local compute",
    "ponens-no-trace": "$0 (no model call)", "ponens-agent-trace": "$0 API, local compute",
}
SPLIT_NOTE = {
    "test-seen": "134 changes, 76 defective, 58 clean. Families authored by the benchmark builder; generated with a fresh seed.",
    "test-heldout": "136 changes, 88 defective, 48 clean. 24 families authored independently by a second model lineage, sealed before any scoring.",
}


DISPUTED_FILE = ROOT / "bench/key/disputed.json"


def load_disputed(split: str) -> set:
    """Ids of clean labels in `split` disputed since v1.1 (empty set if the file is absent)."""
    if not DISPUTED_FILE.exists():
        return set()
    return {d["id"] for d in json.loads(DISPUTED_FILE.read_text())["disputed"] if d["split"] == split}


def is_ponens(arm: str) -> bool:
    return arm.startswith("ponens-")


def native_status(vs: dict, ids: set) -> str:
    """The Ponens CI action's own job status, from meta.ci_status / meta.ci_exit_code of each verdict in scope."""
    c = Counter()
    for vid in ids:
        m = (vs.get(vid) or {}).get("meta") or {}
        c[(m.get("ci_status", "missing"), m.get("ci_exit_code"))] += 1
    total = sum(c.values())
    return "; ".join(f"`{st}` (exit {code}) {n}/{total}" for (st, code), n in sorted(c.items(), key=lambda kv: -kv[1]))


def usd_cell(arm: str, s: dict) -> str:
    if arm not in COST:
        return f"${s['usd_total']:.2f} as recorded in the verdicts" if s["usd_total"] else "not recorded"
    if COST[arm] == "Bedrock list price":
        per = s["usd_total"] / s["n"] if s["n"] else 0
        return f"${s['usd_total']:.2f} (${per:.2f}/change, Bedrock list price)"
    return COST[arm]


def subset_caption(full_rows: list[tuple[str, dict]]) -> str:
    only = [dict(ARMS)[arm] for arm, _ in ARMS if arm not in dict(full_rows)]
    if not only:
        return "The random subset on which every reviewer ran first; every reviewer later covered the whole split."
    return ("The random subset on which every reviewer ran, including the one that ran only on it " if len(only) == 1
            else "The random subset on which every reviewer ran, including those that ran only on it ") + "(" + ", ".join(only) + ")."


def table(rows: list[tuple[str, dict]], native: dict | None = None) -> str:
    """`native` maps arm -> Native action status cell; non-Ponens reviewers have none and show n/a."""
    native = native or {}
    out = ["| Reviewer | Changes | False all-clears (of defective) | 95% upper bound | Critical | Clean cleared (of clean) | False alarms | Clean held | Errors | Native action status | USD | s/change |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm, s in rows:
        label = dict(ARMS)[arm]
        out.append(f"| {label} | {s['n']} | {s['false_all_clear']}/{s['n_defect']} | {s['false_all_clear_upper95'] * 100:.1f}% | "
                   f"{s['critical_false_all_clear']} | {s['clean_cleared']}/{s['n_clean']} | {s['false_alarm']} | {s['clean_held']} | "
                   f"{s['errors']} | {native.get(arm, 'n/a')} | {usd_cell(arm, s)} | {s['elapsed_s_mean']:.0f} |")
    return "\n".join(out)


def family_breakdown(key: dict, verdicts: dict, subset: set | None) -> dict:
    fam_n = Counter()
    missed, rejected, held = Counter(), Counter(), Counter()
    for vid, lab in key["variants"].items():
        if subset is not None and vid not in subset:
            continue
        fam_n[(lab["family"], lab["mode"])] += 1
        v = verdicts.get(vid) or {}
        dec = v.get("decision")
        if lab["mode"] == "defect" and dec == "ACCEPT":
            missed[lab["family"]] += 1
        if lab["mode"] == "clean" and dec == "REJECT":
            rejected[lab["family"]] += 1
        if lab["mode"] == "clean" and dec == "HOLD":
            held[lab["family"]] += 1
    fmt = lambda c, mode: {f: f"{n}/{fam_n[(f, mode)]}" for f, n in sorted(c.items())}  # noqa: E731
    return {"missed_defect_families": fmt(missed, "defect"), "rejected_clean_families": fmt(rejected, "clean"),
            "held_clean_families": fmt(held, "clean")}


def fam_line(d: dict) -> str:
    return ", ".join(f"`{f}` {n}" for f, n in d.items()) if d else "none"


def build(runs_dir: Path = ROOT / "runs") -> tuple[str, dict]:
    custom = runs_dir.resolve() != (ROOT / "runs").resolve()
    md = ["# Results", "",
          "Generated by `scripts/results.py` from the verdict files under `runs/` and the keys under `bench/key/`. "
          "Metric definitions are in PROTOCOL.md. False all-clear: ACCEPT on a change that violates an obligation. "
          "The 95% figure is the one-sided Clopper-Pearson upper bound on the false all-clear rate. "
          "Every number carries its split; the two splits are not pooled. "
          "Corrections to the 27 October release are in `CORRECTIONS.md`.", ""]
    report: dict = {}
    for split in SPLITS:
        key = json.loads((ROOT / "bench/key" / f"{split}.json").read_text())
        subset_file = runs_dir / split / "subset-paid.txt"
        if not subset_file.exists():
            subset_file = ROOT / "runs" / split / "subset-paid.txt"
        subset = set(subset_file.read_text().split())
        n_def = sum(v["mode"] == "defect" for v in key["variants"].values())
        # A replication directory only reports the arms it contains; the published runs/ reports every arm.
        arms = [(a, l) for a, l in ARMS if not custom or (runs_dir / split / a).is_dir()]
        if not arms:
            continue
        md += [f"## {split}", "", SPLIT_NOTE[split] if not custom else
               f"{len(key['variants'])} changes, {n_def} defective, {len(key['variants']) - n_def} clean (the published key for this split).", ""]
        full_rows, sub_rows, fam, native_full, native_sub = [], [], {}, {}, {}
        all_vs = {}
        report[split] = {"n": len(key["variants"]), "n_defect": n_def, "full": {}, "common_subset": {}, "families": {}}
        for arm, _ in arms:
            vs = load_verdicts(runs_dir / split / arm)
            all_vs[arm] = vs
            covered = set(vs) & set(key["variants"])
            is_full = len(covered) >= 0.9 * len(key["variants"])
            if is_full:
                s = score(key, vs)
                full_rows.append((arm, s))
                report[split]["full"][arm] = {k: v for k, v in s.items() if k not in ("by_family", "false_all_clear_variants")}
                report[split]["families"][arm] = {"scope": "full", **family_breakdown(key, vs, None)}
                if is_ponens(arm):
                    native_full[arm] = native_status(vs, set(key["variants"]))
                    report[split]["full"][arm]["native_action_status"] = native_full[arm]
            else:
                report[split]["families"][arm] = {"scope": "common subset", **family_breakdown(key, vs, subset)}
            s2 = score(key, vs, subset)
            sub_rows.append((arm, s2))
            report[split]["common_subset"][arm] = {k: v for k, v in s2.items() if k not in ("by_family", "false_all_clear_variants")}
            if is_ponens(arm):
                native_sub[arm] = native_status(vs, subset)
                report[split]["common_subset"][arm]["native_action_status"] = native_sub[arm]
        md += [f"### All changes ({len(key['variants'])})", "",
               "Reviewers that ran on every change of the split.", "", table(full_rows, native_full), "",
               f"### Common subset ({len(subset)} changes, {sum(key['variants'][v]['mode'] == 'defect' for v in subset)} defective)", "",
               subset_caption(full_rows), "", table(sub_rows, native_sub), ""]
        disputed = load_disputed(split)
        if disputed and not custom:
            dkey = {**key, "variants": {v: lab for v, lab in key["variants"].items() if v not in disputed}}
            d_def = sum(v["mode"] == "defect" for v in dkey["variants"].values())
            d_rows, d_native = [], {}
            report[split]["disputed_excluded"] = {"n": len(dkey["variants"]), "n_defect": d_def, "excluded": sorted(disputed), "full": {}}
            for arm, _ in arms:
                if arm not in report[split]["full"]:
                    continue
                s3 = score(dkey, all_vs[arm])
                d_rows.append((arm, s3))
                report[split]["disputed_excluded"]["full"][arm] = {k: v for k, v in s3.items() if k not in ("by_family", "false_all_clear_variants")}
                if is_ponens(arm):
                    d_native[arm] = native_status(all_vs[arm], set(dkey["variants"]))
                    report[split]["disputed_excluded"]["full"][arm]["native_action_status"] = d_native[arm]
            md += [f"### {split}, disputed labels excluded ({len(dkey['variants'])} changes, {d_def} defective, "
                   f"{len(dkey['variants']) - d_def} clean)", "",
                   f"The tables above are the original, unchanged. These {len(disputed)} clean labels are disputed since v1.1 and are "
                   "listed with their reasons in `bench/key/disputed.json` and `CORRECTIONS.md`; they are excluded here. "
                   "No defect label is disputed, so false all-clears are unchanged.", "", table(d_rows, d_native), ""]
        md += ["### By family", "",
               "For each reviewer: the defect families it missed (false all-clears) and the clean families it rejected "
               "(false alarms) or held, as `family caught-or-missed/family size`. Reviewers scored on the common subset "
               "are marked.", ""]
        for arm, label in arms:
            f = report[split]["families"][arm]
            scope = "" if f["scope"] == "full" else " (common subset)"
            md += [f"**{label}{scope}**", "",
                   f"- Missed defect families: {fam_line(f['missed_defect_families'])}",
                   f"- Rejected clean families: {fam_line(f['rejected_clean_families'])}",
                   f"- Held clean families: {fam_line(f['held_clean_families'])}", ""]
    return "\n".join(md).rstrip() + "\n", report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--runs-dir", type=Path, default=ROOT / "runs",
                    help="directory laid out as <dir>/<split>/<arm>/v-*.json (default: the published runs/). "
                         "Any other directory is a replication: outputs go to <dir>/RESULTS.md and <dir>/results.json.")
    ap.add_argument("--extra-arm", nargs=2, action="append", default=[], metavar=("NAME", "LABEL"),
                    help="score the arm directory NAME under --runs-dir with table label LABEL; repeatable. "
                         "If NAME is already a published arm, only its label changes.")
    a = ap.parse_args(argv)
    for name, label in a.extra_arm:
        for i, (arm, _) in enumerate(ARMS):
            if arm == name:
                ARMS[i] = (name, label)
                break
        else:
            ARMS.append((name, label))
    runs_dir = a.runs_dir.resolve()
    md, report = build(runs_dir)
    js = json.dumps(report, indent=2) + "\n"
    custom = runs_dir != (ROOT / "runs").resolve()
    md_path, js_path = (runs_dir / "RESULTS.md", runs_dir / "results.json") if custom else (ROOT / "RESULTS.md", ROOT / "reports" / "results.json")
    if a.check:
        ok = md_path.exists() and md_path.read_text() == md and js_path.exists() and js_path.read_text() == js
        print(f"{md_path.name} and {js_path.name} match the verdicts" if ok else "MISMATCH: regenerate with scripts/results.py")
        return 0 if ok else 1
    js_path.parent.mkdir(exist_ok=True)
    md_path.write_text(md)
    js_path.write_text(js)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
