#!/usr/bin/env python3
"""Claude arms on Amazon Bedrock, Claude Opus 5.5. Paid: every run is priced and logged.

    python -m baselines.claude.run --mode packet  --variant DIR ...   # arm opus-packet
    python -m baselines.claude.run --mode agentic --variant DIR ...   # arm claude-code

Needs boto3 and an AWS profile with Bedrock access to `us.anthropic.claude-opus-5-5` (system inference profile) in
us-east-1: KB_AWS_PROFILE (default `default`) and KB_AWS_REGION select them; see common/bedrock.py. The runner never
logs in: if the profile has no working credentials it stops with a message.

packet mode (no tools): one InvokeModel call with Anthropic's native Messages body: system = prompts/review.md,
  user = the review packet, adaptive thinking (Opus 5.5 can't disable it), output_config.effort = --effort
  (default high), max_tokens 32000.
agentic mode: Claude Code (`claude -p`, --claude-cli, default ~/.local/bin/claude, version recorded) with
  CLAUDE_CODE_USE_BEDROCK=1, --model us.anthropic.claude-opus-5-5 (also used for its small/fast background model),
  and --max-budget-usd per variant (default 8). AWS access is a read-only (0400) config + credentials pair holding
  fresh short-lived role credentials for the profile, written into the run's private config dir; the environment
  carries AWS_PROFILE, AWS_REGION, AWS_CONFIG_FILE and AWS_SHARED_CREDENTIALS_FILE only.

Cost: real token counts (InvokeModel usage block; Claude Code's per-model usage) x Bedrock list price
(common/bedrock.py), written to meta.usd and appended to runs/cost-ledger.jsonl for every run that reached the
model. --max-usd stops a batch before the ledger total would pass a limit (the $500 cap always applies);
the pre-run ceiling is $0.05 + packet tokens x input price + 32k output tokens (packet) or --max-budget-usd
(agentic).

Isolation (agentic; details in baselines/README.md): throwaway workspace under ~/kab-worker/runs/<rand>/ (variant
copy with .git/config cut to core settings and hooks removed, throwaway HOME/TMPDIR, private CLAUDE_CONFIG_DIR,
scratch); minimal environment (PATH, HOME, TMPDIR, LANG, git lockdown variables, the AWS variables above, Claude
Code switches, JAVA_HOME/JUNIT_JAR/PYTHON); settings only from the private --settings file (--setting-sources user);
default permission mode with the read-only allowlist (Read, Grep, Glob; Bash only for `sh ci/run-tests.sh`,
`sh ci/run-controls.sh`, `git diff`, `git log`, `git show`; --output/--ext-diff/--textconv denied); Claude Code's
own Bash sandbox on (no network, writes only in the copy, scratch and throwaway HOME, no unsandboxed fallback);
reads of credential and personal paths denied; verdict = the final message. Saved outputs are redacted.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from baselines.common import bedrock, cliarm, prompts  # noqa: E402
from baselines.common.ledger import append as ledger_append  # noqa: E402
from baselines.common.packet import build_packet, catalog_ids_from, estimate_tokens, load_catalog  # noqa: E402
from baselines.common.runner import ReviewResult, StopBatch, add_common_args, drive  # noqa: E402
from baselines.common.variant import load_variant  # noqa: E402
from baselines.common.verdict import register_secret  # noqa: E402

MAX_TOKENS = 32000
SWITCHES = {"DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1", "CLAUDE_CODE_NO_MODEL_FALLBACK": "1",
            "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1"}
AGENTIC_TOOLS = "Read,Grep,Glob,Bash"
AGENTIC_ALLOW = ["Read", "Grep", "Glob",
                 "Bash(sh ci/run-tests.sh:*)", "Bash(sh ci/run-controls.sh:*)",
                 "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)"]
DENY_TOOLS = ["Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch", "RemoteTrigger", "Task"]
GIT_DENY = [f"Bash(git {sub} {flag}{tail})" for sub in ("diff", "log", "show")
            for flag in ("--output", "--ext-diff", "--textconv")
            for tail in (":*", "*")] + [f"Bash(git {sub} *{flag}*)" for sub in ("diff", "log", "show")
                                        for flag in ("--output", "--ext-diff", "--textconv")]


def sensitive_paths() -> list:
    home = str(Path.home())
    return [f"{home}/{name}" for name in cliarm.SENSITIVE_HOME]


def deny_read_rules(extra=()) -> list:
    """Absolute-path (`//` prefix) Read deny rules: credential and personal paths in the real home, plus extras."""
    rules = []
    for p in [*sensitive_paths(), *map(str, extra)]:
        rules += [f"Read(/{p})", f"Read(/{p}/**)"]
    return rules


def cli_version(cli: Path) -> str:
    r = subprocess.run([str(cli), "--version"], capture_output=True, text=True, timeout=60,
                       env={"PATH": cliarm.cli_path(), "HOME": str(Path.home()), "DISABLE_AUTOUPDATER": "1"})
    return (r.stdout.strip().split() or ["?"])[0]


def claude_code_usage(result: dict) -> dict:
    """Token totals from Claude Code's result event: modelUsage (per model, camelCase) when present, else usage."""
    tot = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    mu = result.get("modelUsage") or {}
    if mu:
        for m in mu.values():
            tot["input_tokens"] += int(m.get("inputTokens") or 0)
            tot["output_tokens"] += int(m.get("outputTokens") or 0)
            tot["cache_read_input_tokens"] += int(m.get("cacheReadInputTokens") or 0)
            tot["cache_creation_input_tokens"] += int(m.get("cacheCreationInputTokens") or 0)
    else:
        u = result.get("usage") or {}
        for k in tot:
            tot[k] = int(u.get(k) or 0)
    return tot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("packet", "agentic"), required=True)
    ap.add_argument("--model", default=bedrock.OPUS)
    ap.add_argument("--effort", default="high", help="output_config.effort (packet) / --effort (agentic)")
    ap.add_argument("--profile", default=bedrock.PROFILE)
    ap.add_argument("--claude-cli", default=os.environ.get("KB_CLAUDE_CLI", "~/.local/bin/claude"))
    ap.add_argument("--expect-version", default=os.environ.get("KB_CLAUDE_VERSION"))
    ap.add_argument("--max-budget-usd", type=float, default=8.0, help="agentic: Claude Code's per-variant cap")
    ap.add_argument("--work-root", default=os.environ.get("KB_WORK_ROOT", "~/kab-worker/runs"))
    ap.add_argument("--timeout", type=float, default=None, help="seconds per variant (packet 1800, agentic 2700)")
    ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--env", action="append", default=[], help="JAVA_HOME=, JUNIT_JAR=, PYTHON= for ci/ scripts")
    add_common_args(ap)
    a = ap.parse_args(argv)

    cliarm.guard_env()
    bedrock.check_credentials(a.profile)
    arm = a.arm or ("opus-packet" if a.mode == "packet" else "claude-code")
    timeout = a.timeout or (1800.0 if a.mode == "packet" else 2700.0)
    ptext, psha = prompts.load("review.md" if a.mode == "packet" else "review-agentic.md")
    price = bedrock.PRICE[a.model]

    if a.mode == "packet":
        def estimate(vdir: Path) -> float:
            pk = build_packet(load_variant(vdir))
            return 0.05 + (pk.tokens_est + estimate_tokens(ptext)) * 1.2 * price["in"] / 1e6 + MAX_TOKENS * price["out"] / 1e6

        def review(vdir: Path) -> ReviewResult:
            v = load_variant(vdir)
            pk = build_packet(v)
            body = {"max_tokens": MAX_TOKENS, "system": ptext,
                    "messages": [{"role": "user", "content": pk.text}],
                    "output_config": {"effort": a.effort}}
            meta = {"model": a.model, "mode": "packet", "effort": a.effort, "region": bedrock.REGION, "prompt_sha256": psha,
                    "packet_sha256": pk.sha256, "packet_tokens_est": pk.tokens_est, "max_tokens": MAX_TOKENS}
            resp = bedrock.invoke_messages(body, model=a.model, profile=a.profile, read_timeout=int(timeout))
            u = resp.get("usage") or {}
            usage = {k: int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                     "cache_creation_input_tokens")}
            cost = bedrock.usd(usage, a.model)
            ledger_append(arm, v.id, cost, bedrock.PRICE_BASIS)
            text = "".join(b.get("text", "") for b in resp.get("content") or [] if b.get("type") == "text")
            meta.update({"tokens_in": usage["input_tokens"] + usage["cache_read_input_tokens"]
                         + usage["cache_creation_input_tokens"], "tokens_out": usage["output_tokens"],
                         "tokens_detail": usage, "usd": cost, "usd_basis": bedrock.PRICE_BASIS,
                         "stop_reason": resp.get("stop_reason"), "response_model": resp.get("model"),
                         "content_types": [b.get("type") for b in resp.get("content") or []]})
            if resp.get("stop_reason") == "max_tokens":
                meta["error"] = f"output hit max_tokens={MAX_TOKENS}"
            elif resp.get("stop_reason") == "refusal":
                meta["error"] = f"refusal: {json.dumps(resp.get('stop_details'))[:300]}"
            raw = {"response.json": resp, "packet.md": pk.text}
            return ReviewResult(text=text, meta=meta, raw=raw, catalog_ids=pk.catalog_ids)

        return drive(a, arm, review, estimate=estimate)

    # ------------------------------------------------------------------ agentic
    cli = Path(os.path.expanduser(a.claude_cli))
    if not cli.exists():
        raise SystemExit(f"claude CLI not found at {cli}")
    version = cli_version(cli)
    if a.expect_version and version != a.expect_version:
        raise SystemExit(f"{cli} is claude {version}, expected {a.expect_version}")
    toolchain = cliarm.toolchain_env(a.env)

    def review(vdir: Path) -> ReviewResult:
        v = load_variant(vdir)
        raw_cat, _ = load_catalog(v)
        ids = catalog_ids_from(raw_cat)
        ws = cliarm.workspace(vdir, a.work_root)
        try:
            aws = bedrock.write_profile_files(ws.cfg / "aws", a.profile)
            for sec in json.loads(aws.pop("_secrets")):
                register_secret(sec)
            aws.pop("_expires")
            (ws.cfg / "mcp.json").write_text(json.dumps({"mcpServers": {}}))
            settings = {
                "disableAllHooks": True,
                "permissions": {"defaultMode": "default",
                                "deny": DENY_TOOLS + GIT_DENY + deny_read_rules([ws.cfg])},
                "sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                            "autoAllowBashIfSandboxed": False,
                            "filesystem": {"allowWrite": [str(ws.scratch), str(ws.home)],
                                           "denyRead": [*sensitive_paths(), str(ws.cfg)]},
                            "network": {"allowedDomains": [], "allowLocalBinding": False,
                                        "allowAllUnixSockets": False}},
            }
            (ws.cfg / "settings.json").write_text(json.dumps(settings))
            env = cliarm.minimal_env(ws, {**SWITCHES, **toolchain, **aws, "CLAUDE_CONFIG_DIR": str(ws.cfg),
                                          "CLAUDE_CODE_USE_BEDROCK": "1",
                                          "ANTHROPIC_SMALL_FAST_MODEL": a.model,
                                          "ANTHROPIC_DEFAULT_HAIKU_MODEL": a.model})
            prompt = prompts.render(ptext, {"VARIANT_DIR": str(ws.variant), "SCRATCH_DIR": str(ws.scratch)})
            argv = [str(cli), "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "default",
                    "--tools", AGENTIC_TOOLS, "--add-dir", str(ws.variant), str(ws.scratch),
                    "--model", a.model, "--effort", a.effort, "--max-budget-usd", str(a.max_budget_usd),
                    "--strict-mcp-config", "--mcp-config", str(ws.cfg / "mcp.json"),
                    "--setting-sources", "user", "--settings", str(ws.cfg / "settings.json"),
                    "--no-session-persistence",
                    "--allowedTools", *AGENTIC_ALLOW, "--disallowedTools", *DENY_TOOLS, *GIT_DENY]
            run = cliarm.run_cli(argv, cwd=ws.repo, env=env, timeout_s=timeout, stdin_text=prompt, log_dir=ws.logs)
            result, init = {}, {}
            for line in run.stdout.splitlines():
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("type") == "result":
                    result = ev
                elif ev.get("type") == "system" and ev.get("subtype") == "init":
                    init = ev
            usage = claude_code_usage(result)
            cost = bedrock.usd(usage, a.model)
            if any(usage.values()):
                ledger_append(arm, v.id, cost, bedrock.PRICE_BASIS)
            meta = {"model": a.model, "mode": "agentic", "effort": a.effort, "region": bedrock.REGION,
                    "prompt_sha256": psha, "cli": cli.name, "cli_version": version,
                    "init_model": init.get("model"), "init_tools": init.get("tools"),
                    "init_permission_mode": init.get("permissionMode"), "api_key_source": init.get("apiKeySource"),
                    "elapsed_s": run.elapsed_s, "num_turns": result.get("num_turns"),
                    "tokens_in": usage["input_tokens"] + usage["cache_read_input_tokens"]
                    + usage["cache_creation_input_tokens"], "tokens_out": usage["output_tokens"],
                    "tokens_detail": usage, "usd": cost, "usd_basis": bedrock.PRICE_BASIS,
                    "cli_total_cost_usd": result.get("total_cost_usd"),
                    "permission_denials": len(result.get("permission_denials") or []),
                    "agent_instruction_files": ws.agent_files(), "git_config_removed": ws.git_removed}
            raw = {"cli.stdout": run.stdout, "cli.stderr": run.stderr}
            if init.get("permissionMode") not in (None, "default"):
                raise StopBatch(f"CLI reports permissionMode={init.get('permissionMode')!r}; expected default")
            if run.timed_out:
                meta["error"] = f"timed out after {timeout:.0f}s"
            text = result.get("result") if isinstance(result.get("result"), str) else None
            if run.returncode != 0 or result.get("is_error") or not result:
                blob = (text or "") + "\n" + run.stderr[-3000:]
                if "ExpiredToken" in blob or cliarm.looks_auth_failed(blob):
                    raise StopBatch(f"AWS credentials failed: {blob.strip()[-300:]}")
                meta.setdefault("error", f"claude exit {run.returncode}: {blob.strip()[-300:]}")
            return ReviewResult(text=text, meta=meta, raw=raw, catalog_ids=ids)
        finally:
            if not a.keep_work:
                ws.cleanup()

    return drive(a, arm, review, estimate=lambda vdir: a.max_budget_usd)


if __name__ == "__main__":
    raise SystemExit(main())
