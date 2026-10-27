"""Dev pack: builder-authored families used to build and iterate the engine (never headline numbers)."""
from __future__ import annotations

from ...prior import attach_prior  # noqa: F401
from . import payments, process

NAME = "dev"
FAMILIES = payments.FAMILIES + process.FAMILIES
try:
    from . import mortgage
    FAMILIES = FAMILIES + mortgage.FAMILIES
except ImportError:
    pass
