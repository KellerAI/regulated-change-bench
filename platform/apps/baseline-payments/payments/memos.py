"""Payment memos: the free text a payee sees on their remittance."""

import re

from .errors import ValidationError

MEMO_MAX_LENGTH = 140
_WHITESPACE = re.compile(r"\s+")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_LONG_DIGIT_RUN = re.compile(r"\d{8,}")


def normalize(text: str | None) -> str:
    if text is None:
        return ""
    cleaned = _WHITESPACE.sub(" ", text).strip()
    if _CONTROL_CHARACTERS.search(cleaned):
        raise ValidationError("memo contains control characters")
    if len(cleaned) > MEMO_MAX_LENGTH:
        raise ValidationError(f"memo is longer than {MEMO_MAX_LENGTH} characters")
    if _LONG_DIGIT_RUN.search(cleaned):
        raise ValidationError("memo must not contain account or card numbers")
    return cleaned
