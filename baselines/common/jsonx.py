"""Robust extraction of the verdict JSON object from free-form model output.

Models wrap their answer in many ways: <think>...</think> blocks, gpt-oss harmony channel markers, ```json fences,
prose before and after, several drafts. Strategy:
  1. strip reasoning blocks (<think>, <thinking>, <reasoning>, harmony analysis channels);
  2. collect every balanced top-level {...} span (a string-aware scanner, not a regex);
  3. try json.loads on each, then a light repair (smart quotes, trailing commas, // comments) on failures;
  4. prefer the LAST object that has a "decision" key, else the last object with "obligations", else the last object.
Returns (obj or None, method) where method says how it was found, for the verdict's meta.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple

_THINK = re.compile(r"<(think|thinking|reasoning|analysis)>.*?</\1>", re.S | re.I)
_HARMONY_ANALYSIS = re.compile(r"<\|channel\|>analysis<\|message\|>.*?(?=<\|start\|>|<\|channel\|>|$)", re.S)
_HARMONY_TOKENS = re.compile(r"<\|[a-z_]+\|>")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_LINE_COMMENT = re.compile(r"(?m)^\s*//.*$")


def strip_reasoning(text: str) -> str:
    text = _THINK.sub("", text)
    # an unclosed <think> at the start: drop everything up to the last </think> if present
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    text = _HARMONY_ANALYSIS.sub("", text)
    text = _HARMONY_TOKENS.sub("\n", text)
    return text


def balanced_objects(text: str) -> List[str]:
    """Every top-level balanced {...} span, string- and escape-aware."""
    out, depth, start, in_str, esc = [], 0, -1, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"' and depth > 0:
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(text[start:i + 1])
                start = -1
    return out


def _repair(s: str) -> str:
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = _LINE_COMMENT.sub("", s)
    s = _TRAILING_COMMA.sub(r"\1", s)
    return s


def _loads(s: str) -> Tuple[Optional[Any], bool]:
    try:
        return json.loads(s), False
    except ValueError:
        pass
    try:
        return json.loads(_repair(s)), True
    except ValueError:
        return None, False


def extract_json(text: Optional[str], want_key: str = "decision") -> Tuple[Optional[dict], str]:
    if not text or not text.strip():
        return None, "empty"
    # whole text first (a constrained-decoding answer is exactly one object)
    obj, repaired = _loads(text.strip())
    if isinstance(obj, dict):
        return obj, "whole" + ("+repair" if repaired else "")
    cleaned = strip_reasoning(text)
    found: List[Tuple[dict, bool]] = []
    for span in balanced_objects(cleaned):
        o, rep = _loads(span)
        if isinstance(o, dict):
            found.append((o, rep))
    if not found and cleaned is not text:
        for span in balanced_objects(text):
            o, rep = _loads(span)
            if isinstance(o, dict):
                found.append((o, rep))
    if not any(want_key in o for o, _ in found):
        # an unbalanced brace in prose can hide the real object inside a bogus span: decode from every '{'
        dec = json.JSONDecoder()
        for src in (cleaned, _repair(cleaned)):
            for m in re.finditer(r"\{", src):
                try:
                    o, _end = dec.raw_decode(src, m.start())
                except ValueError:
                    continue
                if isinstance(o, dict) and want_key in o:
                    found.append((o, src is not cleaned))
            if any(want_key in o for o, _ in found):
                break
    if not found:
        return None, "no-json-object"
    for key in (want_key, "obligations"):
        hits = [(o, r) for o, r in found if key in o]
        if hits:
            o, r = hits[-1]
            return o, f"scan:{key}" + ("+repair" if r else "")
    o, r = found[-1]
    return o, "scan:last" + ("+repair" if r else "")
