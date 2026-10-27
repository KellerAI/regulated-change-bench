"""Independent held-out change-acceptance variants."""
from ...prior import attach_prior  # noqa: F401
from .product import FAMILIES as PRODUCT
from .process import FAMILIES as PROCESS
from .evidence import FAMILIES as EVIDENCE

NAME = "heldout"
FAMILIES = [*PRODUCT, *PROCESS, *EVIDENCE]
