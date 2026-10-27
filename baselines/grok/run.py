"""Grok packet arm through the Cursor agent CLI (arm `grok-cli`: the name is historical; no standalone Grok CLI with a
scoped login was available, so Grok 4.7 was reached through Cursor's `agent` CLI).

    python -m baselines.grok.run --model grok-4.7-medium --variants-dir DIR

One `agent -p` call per variant, in Cursor's read-only "ask" mode with its sandbox on, in a throwaway workspace
that holds only the review packet (packet.md). The frozen review prompt (baselines/prompts/review.md) is the
instruction, with one added line pointing at packet.md: the prompt is too large for argv with the packet inline.
Runs in Cursor's cloud. Usage counts against the Cursor plan of the logged-in account; it isn't billed per call,
so usd is recorded as 0 with that basis, and any usage fields Cursor returns are kept in meta.

Environment: KB_CURSOR_AGENT (path to the `agent` binary; default: found on PATH plus ~/.local/bin and Homebrew),
KB_DENY_READ (colon-separated extra HOME-relative paths the process may not read, on top of the default list).
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
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from baselines.common import prompts  # noqa: E402
from baselines.common.packet import build_packet  # noqa: E402
from baselines.common.runner import ReviewResult, add_common_args, drive  # noqa: E402
from baselines.common.redact import redact_obj, redact_text  # noqa: E402
from baselines.common.variant import load_variant  # noqa: E402

HOME = Path.home()
# Cursor needs its own config, the OS credential store and the network; everything else of value under HOME is
# made unreadable (best effort, macOS sandbox-exec).
DENY_READ = [".ssh", ".aws", ".config/gh", ".codex", ".claude", ".claude.json", ".gnupg", ".netrc", ".docker", ".kube",
             "Code", "Documents", "Desktop", "Downloads", ".local/share/uv", ".grokbot"]
DENY_READ += [p for p in os.environ.get("KB_DENY_READ", "").split(":") if p]


def sandbox(cmd: list[str]) -> list[str]:
    paths = " ".join('(subpath "' + str((HOME / d).resolve()) + '")' for d in DENY_READ)
    profile = f"(version 1)(allow default)(deny file-read-data file-read-xattr file-write* (require-any {paths}))"
    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists():
        return ["/usr/bin/sandbox-exec", "-p", profile, *cmd]
    return cmd


AGENT = os.environ.get("KB_CURSOR_AGENT") or shutil.which(
    "agent", path=os.pathsep.join([os.environ.get("PATH", ""), str(HOME / ".local" / "bin"), "/usr/local/bin",
                                   "/opt/homebrew/bin"]))
POINTER = ("\n\nThe review packet for this change is the file `packet.md` in your workspace. Read all of it before "
           "deciding. Answer with the JSON object only.")


def cli_version() -> str:
    r = subprocess.run([AGENT, "--version"], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="grok-4.7-medium")
    ap.add_argument("--timeout", type=float, default=1800.0)
    add_common_args(ap)
    a = ap.parse_args(argv)
    if not AGENT:
        raise SystemExit("Cursor agent CLI not found (set KB_CURSOR_AGENT)")
    version = cli_version()
    arm = a.arm or "grok-cli"
    system, prompt_sha = prompts.load("review.md")

    def review(vdir: Path) -> ReviewResult:
        v = load_variant(vdir)
        pk = build_packet(v)
        ws = Path(tempfile.mkdtemp(prefix="kab-grok-"))
        (ws / "packet.md").write_text(pk.text)
        meta = {"model": a.model, "cli": f"cursor-agent {version}", "mode": "ask (read-only)", "sandbox": "enabled",
                "prompt_sha256": prompt_sha, "packet_sha256": pk.sha256, "packet_tokens_est": pk.tokens_est,
                "usd": 0.0, "usd_basis": "Cursor plan quota; not billed per call"}
        cmd = [AGENT, "-p", "--output-format", "json", "--mode", "ask", "--sandbox", "enabled", "--trust",
               "--workspace", str(ws), "--model", a.model, system + POINTER]
        env = {k: os.environ[k] for k in ("HOME", "PATH", "USER", "LANG", "TMPDIR") if k in os.environ}
        t0 = time.time()
        try:
            r = subprocess.run(sandbox(cmd), capture_output=True, text=True, timeout=a.timeout, env=env, cwd=ws)
        except subprocess.TimeoutExpired:
            return ReviewResult(text=None, meta={**meta, "elapsed_s": round(time.time() - t0, 2), "error": "timeout"},
                                catalog_ids=pk.catalog_ids)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        meta["elapsed_s"] = round(time.time() - t0, 2)
        text, out = None, {}
        try:
            out = json.loads(r.stdout)
            text = out.get("result") or out.get("text")
            for k in ("usage", "duration_ms", "duration_api_ms", "is_error"):
                if k in out:
                    meta[k] = out[k]
            if isinstance(out.get("usage"), dict):
                meta["tokens_in"] = out["usage"].get("inputTokens") or out["usage"].get("input_tokens") or 0
                meta["tokens_out"] = out["usage"].get("outputTokens") or out["usage"].get("output_tokens") or 0
        except ValueError:
            text = r.stdout
        if r.returncode != 0 and not text:
            meta["error"] = f"exit {r.returncode}: {r.stderr[-400:]}"
        return ReviewResult(text=redact_text(text), meta=meta,
                            raw={"response.json": redact_obj(out or {"stdout": r.stdout[-5000:]})}, catalog_ids=pk.catalog_ids)

    return drive(a, arm, review)


if __name__ == "__main__":
    raise SystemExit(main())
