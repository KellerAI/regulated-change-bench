#!/usr/bin/env python3
"""Ponens arms (design.md §5): Imandra's ponens CI action, as a PR would meet it. See baselines/ponens/README.md.

    python3 -m baselines.ponens.run --mode no-trace    --variant DIR ...   # arm ponens-no-trace
    python3 -m baselines.ponens.run --mode agent-trace --variant DIR ...   # arm ponens-agent-trace

Ponens 1.22.0 (MIT), github.com/imandra-ai/ponens at commit 2f91978, installed by the user (README.md). The CI
action's own driver (action/run.py at the same commit) runs exactly as the composite action's "Check the reasoning
trace" step would, inside an export of the change's head commit, with the action's default inputs (fail-on error,
require-trace false, no extra policies, bindings auto, scan off) and no GitHub token (no comment is posted).

no-trace     The PR carries no `.ponens/` trace (no agent published one), so the action reports `no-trace` and exits
             0: the check is green. Decision ACCEPT. Free, about a second.
agent-trace  A local model (gpt-oss:120b on a local Ollama server) plays the PR's coding agent and writes the trace
             content (prompts/ponens-pr-agent.md, given the same review packet the packet arms get). The harness
             builds a ponens 1.15 trace from it (steps -> actions, one ground-truth Diff artifact per commit, one
             ConformanceResult per obligation the agent reported, residuals), sets the bank's goal on it (one
             required acceptance criterion per catalog obligation: component {obligation: <id>}, evidence
             ConformanceResult), publishes it at `.ponens/trace.json` and runs the action. The verdict comes from
             Ponens's own deterministic goal resolution (`ponens trace resolve`), mapped as in the README; the
             action's status (which ignores goals) is kept in meta.ci_status / meta.ci_decision.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from baselines.common import REPO_ROOT, prompts  # noqa: E402
from baselines.common.jsonx import extract_json  # noqa: E402
from baselines.common.packet import build_packet, catalog_ids_from, estimate_tokens, load_catalog  # noqa: E402
from baselines.common.runner import ReviewResult, add_common_args, drive  # noqa: E402
from baselines.common.variant import Variant, load_variant  # noqa: E402
from baselines.ollama.run import OUTPUT_BUDGET, http_json, model_info, size_ctx  # noqa: E402

TOOLS = REPO_ROOT / ".tools"
# Ponens is installed by the user (baselines/ponens/README.md); these point at the CLI, its interpreter and the
# action's driver. Defaults are the .tools/ layout that scripts/setup_tools.sh creates.
PONENS_BIN = Path(os.environ.get("PONENS_BIN", TOOLS / "ponens-venv" / "bin" / "ponens"))
PONENS_PY = Path(os.environ.get("PONENS_PY", TOOLS / "ponens-venv" / "bin" / "python"))
ACTION = Path(os.environ.get("PONENS_ACTION", TOOLS / "ponens-src" / "action" / "run.py"))
PONENS_COMMIT = "2f91978"
PR_AGENT_MODEL = "gpt-oss:120b"

TRACE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "outcome": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["ReadFile", "SearchCode", "EditFile", "CreateFile", "RunCommand",
                                                "RunTests", "Review", "Decision"]},
            "label": {"type": "string"}, "rationale": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}}, "result": {"type": "string"}},
            "required": ["type", "label", "rationale"]}},
        "conformance": {"type": "array", "items": {"type": "object", "properties": {
            "obligation": {"type": "string"},
            "status": {"type": "string", "enum": ["passed", "failed", "partial", "unknown"]},
            "strength": {"type": "string", "enum": ["proof", "tests", "static_analysis", "attested"]},
            "basis": {"type": "string"}, "step": {"type": "integer"}},
            "required": ["obligation", "status", "strength", "basis"]}},
        "residuals": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["assumption", "unverified", "out_of_scope", "limitation",
                                                "open_question"]},
            "severity": {"type": "string", "enum": ["info", "low", "medium", "high", "critical"]},
            "statement": {"type": "string"}, "suggested_check": {"type": "string"}},
            "required": ["kind", "severity", "statement"]}},
    },
    "required": ["title", "outcome", "steps", "conformance", "residuals"],
}

# goal item status (ponens resolve) -> verdict status
ITEM_STATUS = {"done": "shown", "blocked": "refuted", "doing": "open", "todo": "open"}


# ------------------------------------------------------------------ ponens plumbing

def export_head(v: Variant, dest: Path) -> None:
    """The head commit's tree, written blob by blob (Variant.export; no `git archive`, so no filter drivers)."""
    v.export(v.head, dest)


def run_action(workdir: Path) -> dict:
    """Run the action's driver like the composite step does; returns its outputs, exit code and report."""
    out_file = workdir.parent / "github_output.txt"
    out_file.write_text("")
    env = {"PATH": f"{PONENS_BIN.parent}:/usr/bin:/bin", "HOME": str(workdir.parent), "PONENS_BIN": str(PONENS_BIN),
           "GITHUB_OUTPUT": str(out_file), "INPUT_TRACE": "", "INPUT_TRANSCRIPT": "",
           "INPUT_TRANSCRIPT_FORMAT": "claude-code", "INPUT_POLICIES": "", "INPUT_POLICY_FILE": "",
           "INPUT_FAIL_ON": "error", "INPUT_COMMENT": "true", "INPUT_REQUIRE_TRACE": "false",
           "INPUT_STRICT_VALIDATE": "false", "INPUT_BINDINGS": "auto", "INPUT_SCAN": "off", "GH_TOKEN": "",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    t0 = time.time()
    r = subprocess.run([str(PONENS_PY), str(ACTION)], cwd=str(workdir), env=env, capture_output=True, text=True,
                       timeout=600)
    outputs = {}
    for line in out_file.read_text().splitlines():
        k, _, val = line.partition("=")
        outputs[k] = val
    report = workdir / ".ponens-ci" / "report.md"
    return {"exit_code": r.returncode, "outputs": outputs, "elapsed_s": round(time.time() - t0, 2),
            "report": report.read_text() if report.exists() else "", "stdout": r.stdout[-20000:],
            "stderr": r.stderr[-5000:]}


def ponens(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(PONENS_BIN), *args], cwd=str(cwd), capture_output=True, text=True, timeout=300,
                          env={"PATH": f"{PONENS_BIN.parent}:/usr/bin:/bin", "HOME": str(cwd)})


def ci_decision(status: str) -> str:
    """What the action's check means for the PR: green (passed / advisory / no-trace) merges."""
    return {"passed": "ACCEPT", "advisory": "ACCEPT", "no-trace": "ACCEPT", "failed": "REJECT",
            "invalid": "REJECT"}.get(status, "HOLD")


# ------------------------------------------------------------------ trace construction

def build_trace(v: Variant, content: dict, catalog: list, model: str) -> dict:
    commits = v.commits()
    changed = [p for _, p in v.changed_files()]
    actions, artifacts = [], []

    def act(**kw) -> int:
        aid = len(actions) + 1
        actions.append({"id": aid, "category": "activity", "inputs": [], "outputs": [], **kw})
        return aid

    # ground truth: the commits themselves (what `ponens emit` would derive mechanically from the session's edits)
    diff_ids = []
    for c in commits:
        files = [p for p in v.git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", c["sha"]).split()]
        aid = act(type="Commit", label=f"commit {c['sha'][:12]}", rationale=(c["message"].splitlines() or [""])[0])
        did = f"diff_{c['sha'][:12]}"
        artifacts.append({"artifact_id": did, "artifact_type": "Diff", "name": f"diff {c['sha'][:12]}",
                          "producer_action_id": aid, "payload": {"files": files, "commit": c["sha"]}})
        actions[-1]["outputs"].append(did)
        diff_ids.append(did)
    if not diff_ids:  # no commits: one Diff for base..head
        aid = act(type="Commit", label="change", rationale="base..head")
        artifacts.append({"artifact_id": "diff_change", "artifact_type": "Diff", "name": "diff base..head",
                          "producer_action_id": aid, "payload": {"files": changed, "commit": v.head}})
        diff_ids.append("diff_change")
    target = diff_ids[-1]

    # the agent's curated narrative
    step_ids = []
    for s in content.get("steps") or []:
        if not isinstance(s, dict):
            continue
        sid = act(type=str(s.get("type") or "Review"), label=str(s.get("label") or "step")[:200],
                  rationale=str(s.get("rationale") or "")[:2000],
                  **({"result_summary": str(s["result"])[:500]} if s.get("result") else {}),
                  **({"detail": "files: " + ", ".join(map(str, s["files"]))[:1000]} if s.get("files") else {}))
        step_ids.append(sid)
    last = step_ids[-1] if step_ids else actions[-1]["id"]

    # one Specification per catalog obligation (the reference), one ConformanceResult per reported obligation
    ids = {o["id"] for o in catalog}
    for o in catalog:
        artifacts.append({"artifact_id": f"ob_{o['id']}", "artifact_type": "Specification",
                          "name": f"obligation {o['id']}", "producer_action_id": 1,
                          "payload": {"obligation": o["id"], "title": o.get("title", "")}})
    seen = set()
    for c in content.get("conformance") or []:
        if not isinstance(c, dict):
            continue
        oid = str(c.get("obligation") or "")
        if oid not in ids or oid in seen:
            continue
        seen.add(oid)
        step = c.get("step")
        producer = step_ids[step - 1] if isinstance(step, int) and 1 <= step <= len(step_ids) else last
        status = c.get("status") if c.get("status") in ("passed", "failed", "partial", "unknown") else "unknown"
        strength = c.get("strength") if c.get("strength") in ("proof", "tests", "static_analysis",
                                                               "attested") else "attested"
        artifacts.append({"artifact_id": f"cr_{oid}", "artifact_type": "ConformanceResult",
                          "name": f"conformance {oid}", "producer_action_id": producer,
                          "derived_from": [target, f"ob_{oid}"],
                          "payload": {"reference_artifact_id": f"ob_{oid}", "target_artifact_id": target,
                                      "status": status, "evidence_strength": strength, "obligation": oid,
                                      "basis": str(c.get("basis") or "")[:2000]}})
        actions[producer - 1]["outputs"].append(f"cr_{oid}")

    for i, r in enumerate(content.get("residuals") or [], 1):
        if not isinstance(r, dict) or not r.get("statement"):
            continue
        kind = r.get("kind") if r.get("kind") in ("assumption", "unverified", "out_of_scope", "limitation",
                                                  "open_question") else "unverified"
        sev = r.get("severity") if r.get("severity") in ("info", "low", "medium", "high", "critical") else "medium"
        payload = {"kind": kind, "severity": sev, "status": "open", "source": "agent_declared",
                   "statement": str(r["statement"])[:2000], "introduced_by_action_id": last}
        if r.get("suggested_check"):
            payload["suggested_check"] = str(r["suggested_check"])[:1000]
        artifacts.append({"artifact_id": f"r{i}", "artifact_type": "Residual",
                          "name": f"{kind}: {str(r['statement'])[:60]}", "producer_action_id": last,
                          "payload": payload, "summary": str(r["statement"])[:200]})

    title = str(content.get("title") or v.change.get("title") or "change")[:200]
    return {
        "trace_id": f"trace-{v.id}", "spec_version": "1.15", "assistant": "pr-agent", "model": model,
        "timestamp": (v.as_of() or {}).get("as_of") or "2026-01-01T00:00:00Z", "title": title,
        "trigger": {"type": "user_request", "description": str(v.change.get("description") or title)[:2000]},
        "actions": actions, "artifacts": artifacts,
        "outcome": {"type": "completed", "summary": str(content.get("outcome") or "")[:2000]},
        "policies": [], "policy_evaluations": [], "residuals": [],
        "goals": [bank_goal(catalog)], "files_modified": changed, "metrics": {},
    }


def bank_goal(catalog: list) -> dict:
    """The bank's definition of done: every catalog obligation, as a typed acceptance criterion (Goal Contract v0.2
    §3-4) resolved by lineage: a ConformanceResult artifact whose payload names the obligation. No `statement`
    field (ponens treats it as an exact-statement match); the title goes in `label`."""
    return {"id": "bank-obligations", "intent": "The change satisfies every obligation in the bank's catalog.",
            "intent_author": "human", "status": "active", "scope": [o["id"] for o in catalog],
            "intent_clauses": [o["id"] for o in catalog],
            "acceptance": [{"id": o["id"], "label": f"{o['id']}: {o.get('title', '')}",
                            "component": {"obligation": o["id"]}, "evidence": {"artifact": "ConformanceResult"},
                            "required": True, "covers": [o["id"]], "author": "human"} for o in catalog]}


# ------------------------------------------------------------------ verdict mapping

def goal_decision(items: list, ci_status: str) -> str:
    if ci_status == "invalid":
        return "HOLD"
    if ci_status == "failed":
        return "REJECT"
    st = [i.get("status") for i in items if i.get("required", True)]
    if any(s == "blocked" for s in st):
        return "REJECT"
    if st and all(s == "done" for s in st):
        return "ACCEPT"
    return "HOLD"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("no-trace", "agent-trace"), required=True)
    ap.add_argument("--pr-agent-model", default=PR_AGENT_MODEL)
    ap.add_argument("--think", default="high")
    ap.add_argument("--keep-alive", default="15m")
    ap.add_argument("--timeout", type=float, default=3600.0)
    ap.add_argument("--keep-work", action="store_true")
    add_common_args(ap)
    a = ap.parse_args(argv)
    for p in (PONENS_BIN, ACTION):
        if not p.exists():
            raise SystemExit(f"{p} missing: see baselines/ponens/README.md (install)")
    arm = a.arm or f"ponens-{a.mode}"
    version = subprocess.run([str(PONENS_BIN), "--version"], capture_output=True, text=True).stdout.strip()
    info = model_info(a.pr_agent_model) if a.mode == "agent-trace" else None
    ptext, psha = prompts.load("ponens-pr-agent.md")

    def review(vdir: Path) -> ReviewResult:
        v = load_variant(vdir)
        raw_cat, where = load_catalog(v)
        catalog = []
        try:
            doc = json.loads(raw_cat) if raw_cat else {}
            items = doc.get("obligations") if isinstance(doc, dict) else doc
            catalog = [o for o in items or [] if isinstance(o, dict) and o.get("id")]
        except ValueError:
            pass
        ids = catalog_ids_from(raw_cat)
        tmp = Path(tempfile.mkdtemp(prefix="kb-ponens-"))
        try:
            work = tmp / "checkout"
            work.mkdir()
            export_head(v, work)
            meta = {"ponens_version": version, "ponens_commit": PONENS_COMMIT, "usd": 0.0,
                    "usd_basis": "local (Ponens CLI; Ollama PR agent, local model)"}
            raw = {}
            if a.mode == "no-trace":
                ci = run_action(work)
                status = ci["outputs"].get("status", "")
                meta.update({"ci_status": status, "ci_exit_code": ci["exit_code"], "ci_decision": ci_decision(status),
                             "elapsed_s": ci["elapsed_s"]})
                raw["action-report.md"] = ci["report"]
                if ci["exit_code"] not in (0, 1) or not status:
                    meta["error"] = f"action failed: {ci['stderr'][-300:]}"
                verdict = {"decision": ci_decision(status), "obligations": [],
                           "summary": f"Ponens CI action: status `{status}`, exit {ci['exit_code']} "
                                      f"({'green check' if ci['exit_code'] == 0 else 'red check'}). "
                                      "No reasoning trace was published for this change; the action's default "
                                      "(require-trace: false) passes it.", "meta": meta}
                return ReviewResult(text=None, decision_override=verdict, meta={}, raw=raw, catalog_ids=ids)

            # agent-trace: the PR agent writes the trace content
            pk = build_packet(v)
            est = pk.tokens_est + estimate_tokens(ptext)
            num_ctx = size_ctx(est, info["context_length"])
            body = {"model": a.pr_agent_model, "stream": False, "keep_alive": a.keep_alive,
                    "think": {"true": True, "false": False}.get(a.think, a.think),
                    "messages": [{"role": "system", "content": ptext}, {"role": "user", "content": pk.text}],
                    "options": {"num_ctx": num_ctx, "num_predict": OUTPUT_BUDGET, "seed": 7},
                    "format": TRACE_SCHEMA}
            t0 = time.time()
            try:
                resp = http_json("/api/chat", body, timeout=a.timeout)
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"ollama HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
            agent_s = round(time.time() - t0, 2)
            content_text = (resp.get("message") or {}).get("content") or ""
            content, how = extract_json(content_text, want_key="conformance")
            meta.update({"pr_agent_model": a.pr_agent_model, "pr_agent_prompt_sha256": psha,
                         "pr_agent_think": a.think, "pr_agent_s": agent_s, "num_ctx": num_ctx,
                         "tokens_in": int(resp.get("prompt_eval_count") or 0),
                         "tokens_out": int(resp.get("eval_count") or 0), "pr_agent_parse": how,
                         "packet_sha256": pk.sha256, "catalog_ref": where})
            raw["pr-agent-response.json"] = {k: val for k, val in resp.items() if k != "context"}
            if not isinstance(content, dict):
                meta["error"] = "PR agent output unparseable"
                return ReviewResult(text=None, decision_override={"decision": "HOLD", "obligations": [],
                                                                  "summary": "no trace", "meta": meta},
                                    meta={}, raw=raw, catalog_ids=ids)
            trace = build_trace(v, content, catalog, a.pr_agent_model)
            (work / ".ponens").mkdir(exist_ok=True)
            (work / ".ponens" / "trace.json").write_text(json.dumps(trace, indent=1))
            raw["trace.json"] = trace
            ci = run_action(work)
            status = ci["outputs"].get("status", "")
            res = ponens("trace", "resolve", ".ponens/trace.json", "--json", cwd=work)
            items = []
            try:
                goals = json.loads(res.stdout)
                items = next((g.get("acceptance") or [] for g in goals if g.get("id") == "bank-obligations"), [])
            except ValueError:
                meta["error"] = f"ponens resolve failed: {res.stderr[-300:]}"
            raw["action-report.md"] = ci["report"]
            raw["resolve.json"] = res.stdout
            counts = {}
            for it in items:
                counts[it.get("status")] = counts.get(it.get("status"), 0) + 1
            decision = goal_decision(items, status)
            meta.update({"ci_status": status, "ci_exit_code": ci["exit_code"], "ci_decision": ci_decision(status),
                         "ci_goals_met": ci["outputs"].get("goals"), "ci_violations": ci["outputs"].get("violations"),
                         "goal_item_counts": counts, "action_s": ci["elapsed_s"],
                         "elapsed_s": round(agent_s + ci["elapsed_s"], 2)})
            if status == "invalid":
                meta["error"] = "ponens rejected the trace as invalid"
            obligations = [{"id": it.get("id"), "status": ITEM_STATUS.get(it.get("status"), "open"),
                            "note": f"ponens goal item {it.get('status')}"
                                    + (f" (evidence {it.get('evidence_ref')})" if it.get("evidence_ref") else "")}
                           for it in items]
            summary = (f"Ponens resolved the bank's goal: {counts.get('done', 0)} done, {counts.get('blocked', 0)} "
                       f"blocked, {counts.get('doing', 0)} doing, {counts.get('todo', 0)} todo of {len(items)}. "
                       f"The CI action reported `{status}` (goals {ci['outputs'].get('goals')}), which on its own "
                       f"would be {'a green' if ci['exit_code'] == 0 else 'a red'} check.")
            verdict = {"decision": decision, "obligations": obligations, "summary": summary, "meta": meta}
            return ReviewResult(text=None, decision_override=verdict, meta={}, raw=raw, catalog_ids=ids)
        finally:
            if a.keep_work:
                print(f"kept {tmp}", file=sys.stderr)
            else:
                shutil.rmtree(tmp, ignore_errors=True)

    return drive(a, arm, review)


if __name__ == "__main__":
    raise SystemExit(main())
