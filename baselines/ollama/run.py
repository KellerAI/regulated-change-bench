#!/usr/bin/env python3
"""Ollama packet arm (gpt-oss-120b, qwen3.8-27b on a local Ollama server).

    python3 -m baselines.ollama.run --model gpt-oss:120b --variant DIR [--variant DIR ...] | --variants-dir DIR

One /api/chat call per variant: system = baselines/prompts/review.md, user = the review packet. No tools.
- num_ctx is sized per variant: packet estimate x 1.15 + prompt + output budget, rounded up to 8192, capped at the
  model's trained context (131072 gpt-oss, 262144 qwen3.8). A packet that cannot fit is an error verdict, never a
  silent truncation (Ollama truncates the prompt from the front when num_ctx is too small; the runner also checks
  prompt_eval_count against its estimate and flags meta.truncation_suspect).
- Thinking is on (gpt-oss: think="high"; qwen: think=true). The answer is constrained to the verdict JSON schema
  (Ollama `format`), so parse failures are rare; the extractor still handles fences and stray prose.
- meta records Ollama's own counts: prompt_eval_count (tokens_in), eval_count (tokens_out, thinking included),
  and the load / prompt-eval / eval / total durations. usd is 0 (local hardware; no marginal API cost).
Never pulls or deletes models: a model that is not already present is an error.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from baselines.common import prompts  # noqa: E402
from baselines.common.packet import build_packet, estimate_tokens  # noqa: E402
from baselines.common.runner import ReviewResult, add_common_args, drive  # noqa: E402
from baselines.common.variant import load_variant  # noqa: E402

HOST = "http://127.0.0.1:11434"
ARM_NAMES = {"gpt-oss:120b": "gpt-oss-120b", "qwen3.8:27b-mxfp8": "qwen3.8-27b"}
DEFAULT_THINK = {"gpt-oss:120b": "high", "qwen3.8:27b-mxfp8": True}
OUTPUT_BUDGET = 32768          # thinking + answer tokens (num_predict)
CTX_STEP = 8192
CTX_MIN = 16384

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["ACCEPT", "REJECT", "HOLD"]},
        "obligations": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "status": {"type": "string", "enum": ["shown", "open", "refuted"]},
                           "note": {"type": "string"}},
            "required": ["id", "status", "note"]}},
        "summary": {"type": "string"},
    },
    "required": ["decision", "obligations", "summary"],
}


def http_json(path: str, body: dict | None = None, timeout: float = 30.0) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HOST + path, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def model_info(model: str) -> dict:
    tags = http_json("/api/tags")
    names = {m["name"] for m in tags.get("models", [])}
    if model not in names:
        raise SystemExit(f"model {model!r} is not present in Ollama ({sorted(names)}); this runner never pulls")
    show = http_json("/api/show", {"model": model})
    mi = show.get("model_info") or {}
    ctx = next((v for k, v in mi.items() if k.endswith(".context_length")), 32768)
    return {"context_length": int(ctx), "digest": next((m.get("digest") for m in tags["models"] if m["name"] == model),
                                                       None), "details": show.get("details")}


def size_ctx(prompt_tokens_est: int, model_ctx: int) -> int:
    need = int(prompt_tokens_est * 1.15) + 1024 + OUTPUT_BUDGET
    ctx = max(CTX_MIN, int(math.ceil(need / CTX_STEP) * CTX_STEP))
    return min(ctx, model_ctx)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="an Ollama model already pulled, e.g. gpt-oss:120b")
    ap.add_argument("--think", default=None, help="true|false|low|medium|high (default per model)")
    ap.add_argument("--format", choices=("schema", "json", "none"), default="schema",
                    help="constrain the answer: the verdict JSON schema (default), any JSON, or free text")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--keep-alive", default="15m")
    ap.add_argument("--timeout", type=float, default=3600.0, help="seconds per variant")
    add_common_args(ap)
    a = ap.parse_args(argv)

    info = model_info(a.model)
    arm = a.arm or ARM_NAMES.get(a.model) or a.model.replace(":", "-").replace("/", "-")
    think = DEFAULT_THINK.get(a.model, True) if a.think is None else (
        {"true": True, "false": False}.get(a.think.lower(), a.think))
    system, prompt_sha = prompts.load("review.md")

    def review(vdir: Path) -> ReviewResult:
        v = load_variant(vdir)
        pk = build_packet(v)
        est = pk.tokens_est + estimate_tokens(system)
        num_ctx = size_ctx(est, info["context_length"])
        meta = {"model": a.model, "model_digest": info["digest"], "think": think, "format": a.format,
                "num_ctx": num_ctx, "num_predict": OUTPUT_BUDGET, "seed": a.seed, "prompt_sha256": prompt_sha,
                "packet_sha256": pk.sha256, "packet_tokens_est": pk.tokens_est, "usd": 0.0,
                "usd_basis": "local Ollama; no marginal API cost"}
        if int(est * 1.15) + 1024 + OUTPUT_BUDGET > info["context_length"]:
            return ReviewResult(text=None, meta={**meta, "error": f"packet too large: ~{est} tokens for a "
                                                 f"{info['context_length']}-token model"}, catalog_ids=pk.catalog_ids)
        body = {"model": a.model, "stream": False, "keep_alive": a.keep_alive, "think": think,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": pk.text}],
                "options": {"num_ctx": num_ctx, "num_predict": OUTPUT_BUDGET, "seed": a.seed}}
        if a.format == "schema":
            body["format"] = VERDICT_SCHEMA
        elif a.format == "json":
            body["format"] = "json"
        t0 = time.time()
        try:
            resp = http_json("/api/chat", body, timeout=a.timeout)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            return ReviewResult(text=None, meta={**meta, "elapsed_s": round(time.time() - t0, 2),
                                                 "error": f"ollama HTTP {e.code}: {detail}"},
                                catalog_ids=pk.catalog_ids)
        wall = round(time.time() - t0, 2)
        msg = resp.get("message") or {}
        content = msg.get("content") or ""
        thinking = msg.get("thinking") or ""
        ns = 1e9
        pe = int(resp.get("prompt_eval_count") or 0)
        meta.update({
            "elapsed_s": wall,
            "tokens_in": pe,
            "tokens_out": int(resp.get("eval_count") or 0),
            "thinking_chars": len(thinking),
            "answer_chars": len(content),
            "done_reason": resp.get("done_reason"),
            "load_s": round((resp.get("load_duration") or 0) / ns, 2),
            "prompt_eval_s": round((resp.get("prompt_eval_duration") or 0) / ns, 2),
            "eval_s": round((resp.get("eval_duration") or 0) / ns, 2),
            "total_s": round((resp.get("total_duration") or 0) / ns, 2),
            "tokens_est_ratio": round(pe / est, 3) if est else None,
        })
        if pe and pe < 0.6 * est:
            meta["truncation_suspect"] = True
        if resp.get("done_reason") == "length":
            meta["error"] = f"output hit num_predict={OUTPUT_BUDGET} before finishing"
        raw = {"response.json": {k: v for k, v in resp.items() if k != "context"}, "packet.md": pk.text}
        return ReviewResult(text=content, meta=meta, raw=raw, catalog_ids=pk.catalog_ids)

    return drive(a, arm, review)


if __name__ == "__main__":
    raise SystemExit(main())
