"""Bundled reference assets for the TARSUS pipeline.

These files ship with the package so the pipeline is fully self-contained
— no paths to external directories, no extra CLI flags for internal data.
"""

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent

WORKFLOW_TEMPLATE = _ASSETS_DIR / "generic.workflow"
"""FragPipe workflow template used by Steps 3a and 3c."""

SUBS_EXCLUDE_CSV = _ASSETS_DIR / "subs_exclude.csv"
"""Amino acid substitution exclusion matrix used by Step 3b."""
