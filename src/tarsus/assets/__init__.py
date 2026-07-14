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

SIXTY_TWENTY_MASK_CSV = _ASSETS_DIR / "SixtyTwentyMask.csv"
"""Cells to grey out on the 61x19 heatmap — chiefly each codon's cognate (self) cell.

Indexed by **RNA** codon (``UUU``). From the lab's ``SubsToSixtyTwentyWithMask.py``.
"""

NECE_MASK_CSV = _ASSETS_DIR / "NeCEMask.csv"
"""Near-Cognate Error cells — substitutions reachable by a single nucleotide change.

Drawn as small squares on the heatmap. Indexed by **DNA** codon (``ATA``), unlike
:data:`SIXTY_TWENTY_MASK_CSV`. From the lab's ``SubsToSixtyTwentyWithMask.py``.
"""
