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

# The 61x19 heatmap masks (SixtyTwentyMask.csv, NeCEMask.csv) live in this directory
# but are exported from `tarsus.codons`, NOT from here. Deliberate: `orchestration`
# imports step modules lazily, so a long-running master already holds THIS module in
# `sys.modules` from Step 3b. A constant added here mid-run is invisible to it, and a
# freshly-read Step 12 importing that name dies with ImportError on an otherwise
# finished pipeline. See `tarsus.codons` and D-063.
