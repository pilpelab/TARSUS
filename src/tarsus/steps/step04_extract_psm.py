"""Step 4: Extract PSM data for PepQuery validation.

Reads the FragPipe second-pass psm.tsv, filters on Intensity > 0,
and writes peptide sequences (one per line) for PepQuery open search.

FragPipe 24.0 uses internal scan numbering that does not match the
native mzML scan numbers.  PepQuery open search (peptide-only input)
bypasses this by searching all indexed spectra for each peptide,
which is correct for the variant-peptide validation use case.
"""

import csv
from pathlib import Path


def extract_psm(psm_path: Path, output_path: Path) -> None:
    """Extract peptide sequences from FragPipe psm.tsv for PepQuery.

    Output is one peptide per line — no spectrum title column.
    PepQuery open search finds matching spectra automatically.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with psm_path.open("r", newline="") as fin, output_path.open(
        "w", newline=""
    ) as fout:
        reader = csv.DictReader(fin, delimiter="\t")
        writer = csv.writer(fout, delimiter="\t")

        for row in reader:
            try:
                intensity = float(row["Intensity"])
            except (ValueError, KeyError):
                continue
            if intensity <= 0:
                continue
            writer.writerow([row["Peptide"]])
