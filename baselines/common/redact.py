"""Redact token-shaped strings before anything is saved (raw outputs, verdicts, logs).

Patterns: JWTs, Anthropic/OpenAI-style `sk-` keys, GitHub tokens (`ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`,
`github_pat_`), AWS access key ids (AKIA/ASIA), PEM private keys, `Bearer` header values, and long random-looking
base64 runs (>= 40 chars, upper + lower + digit, high entropy, not hex: commit SHAs and sha256 digests stay).
Plus any exact secrets the caller knows (the token it passed). Applied to every raw file and verdict by verdict.py.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Optional

MARK = "[REDACTED]"
_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),          # JWT
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),                                                  # sk-..., sk-ant-...
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),                                             # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                                            # AWS key ids
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{16,}"),
]
_B64 = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{40,}={0,2}(?![A-Za-z0-9+/=_-])")
_HEX = re.compile(r"^[0-9a-fA-F]+$")


def _entropy(s: str) -> float:
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _looks_secret(s: str) -> bool:
    if _HEX.match(s) or s.count("/") > 3:
        return False
    if not (re.search(r"[A-Z]", s) and re.search(r"[a-z]", s) and re.search(r"[0-9]", s)):
        return False
    return _entropy(s) >= 4.3


def redact_text(text: Optional[str], secrets: Iterable[str] = ()) -> Optional[str]:
    if not text:
        return text
    for sec in secrets:
        if sec and len(sec) >= 8:
            text = text.replace(sec, MARK)
    for p in _PATTERNS:
        text = p.sub(lambda m: (m.group(1) + " " + MARK) if p.groups else MARK, text)
    return _B64.sub(lambda m: MARK if _looks_secret(m.group(0)) else m.group(0), text)


def redact_obj(obj, secrets: Iterable[str] = ()):
    secrets = list(secrets)
    if isinstance(obj, str):
        return redact_text(obj, secrets)
    if isinstance(obj, list):
        return [redact_obj(x, secrets) for x in obj]
    if isinstance(obj, dict):
        return {k: redact_obj(v, secrets) for k, v in obj.items()}
    return obj
