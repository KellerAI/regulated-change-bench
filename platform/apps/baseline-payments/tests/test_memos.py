import pytest

from payments.errors import ValidationError
from payments.memos import MEMO_MAX_LENGTH, normalize


def test_whitespace_is_collapsed():
    assert normalize("  Invoice\t 4471 \n September ") == "Invoice 4471 September"


def test_none_becomes_empty():
    assert normalize(None) == ""


def test_length_limit():
    assert normalize("x" * MEMO_MAX_LENGTH) == "x" * MEMO_MAX_LENGTH
    with pytest.raises(ValidationError):
        normalize("x" * (MEMO_MAX_LENGTH + 1))


def test_long_digit_runs_are_refused():
    assert normalize("PO 1234567") == "PO 1234567"
    with pytest.raises(ValidationError):
        normalize("acct 880012345678")


def test_control_characters_are_refused():
    with pytest.raises(ValidationError):
        normalize("bell\x07")
