"""Score arms against an unsealed key.

    python -m bench.score.score --key /tmp/.../test.json --arm runs/test/opus-packet [--arm ...] [--out reports/x.json]

ACCEPT on a defective variant is a false all-clear. Missing or unparseable verdicts count as "not ACCEPT"
and are reported as errors.
"""
import argparse
import json
import math
from pathlib import Path


def binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def cp_upper(k: int, n: int, conf: float = 0.95) -> float:
    """One-sided Clopper-Pearson upper bound for k events in n trials."""
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > 1 - conf:
            lo = mid
        else:
            hi = mid
    return hi


def load_verdicts(arm: Path) -> dict:
    out = {}
    for f in arm.glob("v-*.json"):
        try:
            out[f.stem] = json.loads(f.read_text())
        except ValueError:
            out[f.stem] = {"decision": None, "meta": {"error": "unparseable verdict file"}}
    return out


def score(key: dict, verdicts: dict, subset: set | None = None) -> dict:
    rows = []
    for vid, lab in key["variants"].items():
        if subset is not None and vid not in subset:
            continue
        v = verdicts.get(vid)
        dec = (v or {}).get("decision")
        err = v is None or dec not in ("ACCEPT", "REJECT", "HOLD") or bool((v.get("meta") or {}).get("error"))
        flagged = {o["id"] for o in (v or {}).get("obligations", []) if o.get("status") in ("refuted", "open")}
        rows.append({"variant": vid, "mode": lab["mode"], "family": lab["family"], "pack": lab["pack"],
                     "severity": lab["severity"], "planted": lab["obligations"], "decision": dec if not err or dec in ("ACCEPT", "REJECT", "HOLD") else None,
                     "error": err, "localized": bool(set(lab["obligations"]) & flagged),
                     "usd": float(((v or {}).get("meta") or {}).get("usd") or 0),
                     "elapsed_s": float(((v or {}).get("meta") or {}).get("elapsed_s") or 0)})
    d = [r for r in rows if r["mode"] == "defect"]
    c = [r for r in rows if r["mode"] == "clean"]
    fac = [r for r in d if r["decision"] == "ACCEPT"]
    crit = [r for r in fac if r["severity"] == "critical"]
    res = {
        "n": len(rows), "n_defect": len(d), "n_clean": len(c),
        "false_all_clear": len(fac), "false_all_clear_rate": len(fac) / len(d) if d else None,
        "false_all_clear_upper95": cp_upper(len(fac), len(d)) if d else None,
        "critical_false_all_clear": len(crit),
        "defect_rejected": sum(r["decision"] == "REJECT" for r in d), "defect_held": sum(r["decision"] == "HOLD" for r in d),
        "localized": sum(r["localized"] for r in d if r["decision"] != "ACCEPT"),
        "clean_cleared": sum(r["decision"] == "ACCEPT" for r in c),
        "false_alarm": sum(r["decision"] == "REJECT" for r in c),
        "clean_held": sum(r["decision"] == "HOLD" for r in c),
        "errors": sum(r["error"] for r in rows),
        "missing": sum(1 for r in rows if r["decision"] is None),
        "usd_total": round(sum(r["usd"] for r in rows), 4),
        "elapsed_s_mean": round(sum(r["elapsed_s"] for r in rows) / len(rows), 2) if rows else None,
        "false_all_clear_variants": [{"variant": r["variant"], "family": r["family"], "planted": r["planted"]} for r in fac],
    }
    for k in ("false_alarm", "clean_held", "clean_cleared"):
        res[k + "_rate"] = res[k] / len(c) if c else None
    by_family = {}
    for r in rows:
        f = by_family.setdefault(f"{r['pack']}/{r['family']}/{r['mode']}", {"n": 0, "ACCEPT": 0, "REJECT": 0, "HOLD": 0, "none": 0})
        f["n"] += 1
        f[r["decision"] or "none"] += 1
    res["by_family"] = by_family
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, nargs="+")
    ap.add_argument("--arm", required=True, action="append")
    ap.add_argument("--subset", help="file with one variant id per line")
    ap.add_argument("--out")
    a = ap.parse_args()
    key = {"variants": {}}
    for k in a.key:
        key["variants"].update(json.loads(Path(k).read_text())["variants"])
    subset = set(Path(a.subset).read_text().split()) if a.subset else None
    report = {}
    for arm in a.arm:
        report[Path(arm).name] = score(key, load_verdicts(Path(arm)), subset)
    hdr = f"{'arm':28} {'n':>4} {'def':>4} {'FAC':>4} {'FACub95':>8} {'cleared':>8} {'falarm':>7} {'held':>5} {'err':>4} {'usd':>8} {'s/var':>6}"
    print(hdr)
    for name, r in report.items():
        print(f"{name:28} {r['n']:4d} {r['n_defect']:4d} {r['false_all_clear']:4d} {r['false_all_clear_upper95'] or 0:8.3f} "
              f"{r['clean_cleared']:8d} {r['false_alarm']:7d} {r['clean_held']:5d} {r['errors']:4d} {r['usd_total']:8.2f} {r['elapsed_s_mean'] or 0:6.1f}")
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
