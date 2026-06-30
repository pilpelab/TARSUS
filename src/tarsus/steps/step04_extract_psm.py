"""Step 4: Extract PSM data for PepQuery validation.

Reads the FragPipe second-pass psm.tsv, filters on Intensity > 0,
and writes a two-column TSV: peptide\tspectrum_title for PepQuery.
"""

import csv
from pathlib import Path


def extract_psm(psm_path: Path, output_path: Path) -> None:
    """Extract peptide and spectrum title pairs from FragPipe psm.tsv.

    The Spectrum field has format: <file>_sub.<scan>.<scan>.<charge>
    We strip the _sub suffix and produce: <file>:<scan>:<charge>
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

            parts = row["Spectrum"].split(".")
            file_name = parts[0].split("_sub")[0]
            scan_num = str(int(parts[1]))
            charge = row["Charge"]
            spectrum_title = f"{file_name}:{scan_num}:{charge}"
            writer.writerow([row["Peptide"], spectrum_title])
