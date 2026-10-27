"""Frozen prompts (baselines/prompts/*.md). Each run records the prompt's sha256 so a changed prompt is visible.

The prompt files are plain Markdown. Lines starting with `<!--` up to `-->` at the very top are an authoring note
for maintainers and are stripped before use; `{{NAME}}` placeholders are filled by render().
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Tuple

from . import PROMPTS

_NOTE = re.compile(r"\A\s*<!--.*?-->\s*", re.S)


def load(name: str) -> Tuple[str, str]:
    """(prompt text without the authoring note, sha256 of that text)."""
    raw = (PROMPTS / name).read_text()
    text = _NOTE.sub("", raw, count=1)
    return text, hashlib.sha256(text.encode()).hexdigest()


def render(text: str, values: Dict[str, str]) -> str:
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        raise ValueError(f"unfilled placeholders: {sorted(set(left))}")
    return text
