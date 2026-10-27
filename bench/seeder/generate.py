"""Generate a split of blind variants plus its (plaintext, to-be-sealed) answer key.

    python -m bench.seeder.generate --pack dev --split dev --seed dev-A --count 120 --out work/variants/dev

Steps per variant: build the tree with a family, attach the pack's prior ledger, run the PR's CI on the
CI commit, run the oracle, scrub for leaks, then either keep it (random id) or discard it with a reason.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import importlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .builder import SeedError, VariantBuilder, git, iso
from . import oracles

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "platform"
LEAK = re.compile(r"\b(seed(ed|er)?|defect|planted|oracle|bench(mark)?|clean[ -]twin|answer key|ground truth|family)\b", re.I)


def tool_env(home: Path) -> dict:
    from shared.isolation import tool_env as allowlisted
    return allowlisted(home)


def export_commit(repo: Path, commit: str, dest: Path):
    from shared.isolation import export_tree
    export_tree(repo, commit, dest)


def run_suite(src: Path, app: str, out: Path, extra_files: dict[str, str] | None = None, timeout: int = 600) -> dict:
    """Run ci/run-tests.sh in an exported tree (locally). Returns exit code, junit cases, timing."""
    for rel, text in (extra_files or {}).items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    from shared.isolation import sandboxed
    out.mkdir(parents=True, exist_ok=True)
    home = out.parent / (out.name + "-home")
    home.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = subprocess.run(sandboxed(["/bin/sh", "ci/run-tests.sh", app, str(out)], [src, out, home]), cwd=src,
                       capture_output=True, text=True, env=tool_env(home), timeout=timeout)
    return {"exit": r.returncode, "elapsed_s": round(time.time() - t0, 2), "cases": junit_cases(out),
            "stderr_tail": r.stderr[-2000:], "stdout_tail": r.stdout[-2000:]}


def junit_cases(out: Path) -> dict[str, str]:
    """testcase id -> passed|failed|skipped, across every JUnit XML file in out."""
    cases = {}
    for f in sorted(out.rglob("*.xml")):
        try:
            tree = ET.parse(f)
        except ET.ParseError:
            continue
        for tc in tree.iter("testcase"):
            cid = f"{tc.get('classname', '')}#{tc.get('name', '')}"
            if tc.find("failure") is not None or tc.find("error") is not None:
                cases[cid] = "failed"
            elif tc.find("skipped") is not None:
                cases[cid] = "skipped"
            else:
                cases[cid] = "passed"
    return cases


def load_pack(name: str):
    return importlib.import_module(f"bench.seeder.packs.{name}")


def plan(pack, count: int, rng: random.Random, clean_share: float) -> list[tuple]:
    fams = list(pack.FAMILIES)
    out = []
    i = 0
    while len(out) < count:
        fam = fams[i % len(fams)]
        mode = "clean" if rng.random() < clean_share else "defect"
        if mode not in fam.modes:
            mode = fam.modes[0]
        out.append((fam, mode))
        i += 1
    rng.shuffle(out)
    return out


def build_one(pack, fam, mode: str, seed: str, n: int, work: Path) -> VariantBuilder:
    rng = random.Random(f"{seed}:{n}:{fam.name}:{mode}")
    tmp = work / f"build-{n:04d}"
    if tmp.exists():
        shutil.rmtree(tmp)
    author = ""
    if getattr(fam, "author_role", None):
        from . import people
        author = rng.choice([p for p in people.with_role(fam.author_role, fam.app) if p in people.engineers(fam.app)])
    b = VariantBuilder(platform=PLATFORM, out=tmp, rng=rng, app=fam.app, family=fam.name, pack=pack.NAME, author=author)
    fam.apply(b, mode)
    if b.label_ is None or not b.records:
        raise SeedError(f"{fam.name} did not label or record")
    if hasattr(pack, "attach_prior"):
        pack.attach_prior(b)
    if fam.after_prior:
        fam.after_prior(b, mode)
    b.write_records()
    return b


def run_ci(b: VariantBuilder, scratch: Path) -> dict:
    commit = b.ci_commit or b.head
    src = scratch / "ci-src"
    export_commit(b.repo, commit, src)
    res = run_suite(src, b.app, scratch / "ci-out")
    ci_dir = b.rdir / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted((scratch / "ci-out").rglob("*.xml")):
        shutil.copy(f, ci_dir / f.name)
    started = b.records["approvals"][0]["at"] if b.records.get("approvals") else iso(b.as_of)
    run = {"pipeline": "pr-checks", "commit": commit, "executor": f"ci-runner-{b.rng.randint(1, 9):02d}",
           "started_at": b.records["change"]["commits"][-1]["at"] if commit == b.head else started,
           "result": "success" if res["exit"] == 0 else "failure", "command": f"ci/run-tests.sh {b.app}",
           "reports": sorted(p.name for p in ci_dir.glob("*.xml"))}
    if b.extra.get("ci_started_at"):
        run["started_at"] = b.extra["ci_started_at"]
    (ci_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    return res


def check_oracles(b: VariantBuilder, scratch: Path) -> tuple[bool, list[str]]:
    notes = []
    ok = True
    for o in b.oracles:
        if o["kind"] == "hidden_test":
            src = scratch / f"oracle-src-{len(notes)}"
            export_commit(b.repo, b.head, src)
            res = run_suite(src, b.app, scratch / f"oracle-out-{len(notes)}", extra_files=o["files"])
            got = {k: v for k, v in res["cases"].items() if any(t in k for t in o["tests"])}
            if not got:
                ok = False
                notes.append(f"hidden tests not found: {o['tests']} exit={res['exit']} {res['stderr_tail'][-300:]}")
                continue
            want_fail = o["expect"] == "fail"
            failed = any(v == "failed" for v in got.values())
            if failed != want_fail:
                ok = False
                notes.append(f"hidden test expected {o['expect']}, got {got}")
        elif o["kind"] == "predicate":
            fn = getattr(oracles, o["name"])
            val = fn(b, **o.get("args", {}))
            if val != o["expect"]:
                ok = False
                notes.append(f"predicate {o['name']} expected {o['expect']} got {val}")
        elif o["kind"] == "ci":
            got = {k: v for k, v in b.extra.get("ci_cases", {}).items() if any(t in k for t in o["tests"])}
            failed = any(v == "failed" for v in got.values())
            if not got or failed != (o["expect"] == "fail"):
                ok = False
                notes.append(f"ci expectation {o['expect']} not met: {got}")
        else:
            ok = False
            notes.append(f"unknown oracle kind {o['kind']}")
    if not b.oracles:
        ok = False
        notes.append("no oracle")
    return ok, notes


def scrub(b: VariantBuilder) -> list[str]:
    hits = []
    diff = git(b.repo, "diff", b.base, "HEAD")
    log = git(b.repo, "log", "--format=%an %ae %s %b", f"{b.base}..HEAD")
    for name, text in (("diff", diff), ("log", log)):
        for line in text.splitlines():
            if line.startswith("-"):
                continue
            m = LEAK.search(line)
            if m:
                hits.append(f"{name}: {line.strip()[:120]}")
    for f in b.rdir.rglob("*.json"):
        m = LEAK.search(f.read_text())
        if m:
            hits.append(f"records/{f.relative_to(b.rdir)}: {m.group(0)}")
    return hits


def finalize_one(pack, fam, mode, seed, n, work: Path, outdir: Path) -> dict:
    scratch = Path(tempfile.mkdtemp(prefix=f"kab-{n:04d}-", dir=work))
    try:
        try:
            b = build_one(pack, fam, mode, seed, n, work)
        except SeedError as e:
            return {"n": n, "family": fam.name, "mode": mode, "kept": False, "reason": f"seed: {e}"}
        res = run_ci(b, scratch)
        b.extra["ci_cases"] = res["cases"]
        b.extra["ci_exit"] = res["exit"]
        if not res["cases"]:
            return {"n": n, "family": fam.name, "mode": mode, "kept": False,
                    "reason": f"ci produced no results: {res['stderr_tail'][-400:]}"}
        ok, notes = check_oracles(b, scratch)
        leaks = scrub(b)
        if not ok or leaks:
            return {"n": n, "family": fam.name, "mode": mode, "kept": False,
                    "reason": "; ".join(notes + [f"leak {h}" for h in leaks])[:1500]}
        vid = "v-" + hashlib.sha256(f"{seed}:{n}:{os.urandom(8).hex()}".encode()).hexdigest()[:10]
        dest = outdir / vid
        shutil.move(str(b.out), dest)
        lab = b.label_
        return {"n": n, "family": fam.name, "mode": mode, "kept": True, "variant": vid, "app": b.app,
                "pack": pack.NAME, "obligations": lab.obligations, "severity": lab.severity, "note": lab.note,
                "ci_exit": res["exit"], "ci_s": res["elapsed_s"]}
    except Exception as e:  # keep going; a broken family shouldn't stop the split
        return {"n": n, "family": fam.name, "mode": mode, "kept": False, "reason": f"error: {type(e).__name__}: {e}"[:1500]}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--clean-share", type=float, default=0.4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--key", required=True, help="plaintext key path (sealed afterwards)")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", default="", help="comma list of family names (debug)")
    ap.add_argument("--quiet", action="store_true", help="print counts only, never family names (blind packs)")
    args = ap.parse_args(argv)

    pack = load_pack(args.pack)
    rng = random.Random(f"plan:{args.seed}")
    jobs = plan(pack, args.count, rng, args.clean_share)
    if args.only:
        keep = set(args.only.split(","))
        jobs = [j for j in jobs if j[0].name in keep]
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="kab-work-"))
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(finalize_one, pack, fam, mode, args.seed, n, work, outdir) for n, (fam, mode) in enumerate(jobs)]
        for f in cf.as_completed(futs):
            r = f.result()
            results.append(r)
            status = "kept" if r["kept"] else "DROP"
            if args.quiet:
                if len(results) % 10 == 0:
                    print(f"[{len(results):4d}/{len(jobs)}] kept so far {sum(x['kept'] for x in results)}", flush=True)
            else:
                print(f"[{len(results):4d}/{len(jobs)}] {status} {r['family']}/{r['mode']} {r.get('variant', '')} {r.get('reason', '')[:200]}",
                      flush=True)
    shutil.rmtree(work, ignore_errors=True)
    kept = sorted((r for r in results if r["kept"]), key=lambda r: r["variant"])
    key = {"split": args.split, "pack": args.pack, "seed": args.seed, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "platform_commit": git(ROOT, "rev-parse", "HEAD", check=False),
           "variants": {r["variant"]: {k: r[k] for k in ("family", "mode", "app", "pack", "obligations", "severity", "note")}
                        for r in kept},
           "discarded": [r for r in results if not r["kept"]]}
    Path(args.key).parent.mkdir(parents=True, exist_ok=True)
    Path(args.key).write_text(json.dumps(key, indent=2) + "\n")
    by = {}
    for r in kept:
        by.setdefault(r["mode"], 0)
        by[r["mode"]] += 1
    summary = {"kept": len(kept), "dropped": len(results) - len(kept), "by_mode": by}
    if args.quiet:
        summary["drop_reasons"] = sorted({r["reason"].split(":")[0] for r in results if not r["kept"]})
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    sys.exit(main())
