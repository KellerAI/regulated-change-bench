"""Shared code for the baseline arms (design.md §5): variant loading, the review packet, verdicts, JSON extraction.

Standard library only, Python 3.9+, so the same files run on any machine, including the one that runs the CLI arms.
"""

from pathlib import Path

BASELINES = Path(__file__).resolve().parent.parent
REPO_ROOT = BASELINES.parent
PROMPTS = BASELINES / "prompts"
RUNS = REPO_ROOT / "runs"
