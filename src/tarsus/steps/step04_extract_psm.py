"""Step 4: Extract PSM data for targeted PepQuery validation.

Reads the FragPipe second-pass psm.tsv, filters on Intensity > 0, and writes
one ``peptide<TAB>spectrum_title`` row per PSM — the two-column input PepQuery
needs to validate each candidate peptide against *the spectrum it was actually
identified on*, rather than against any spectrum in the index.

FragPipe writes ``file_sub.scan.scan.charge`` in its ``Spectrum`` column, while
the PepQuery index (built from the original mzML in Step 2) titles spectra
``file:scan:charge``.  The ``_sub`` suffix is therefore stripped here, matching
the reference ``extract_psm.py``.  Scan numbers are preserved across
``_sub.mzML``, so the lookup resolves exactly.

See D-047 in ``.memory/decisions.md``.
"""

import csv
from pathlib import Path


def _spectrum_to_title(spectrum: str, charge: str) -> str:
    """Convert a FragPipe ``Spectrum`` value to a PepQuery index spectrum title.

    ``file_sub.00100.00100.2`` + charge ``2`` -> ``file:100:2``

    The ``_sub`` suffix is stripped and leading zeros are removed from the scan
    number.  Charge is taken from the ``Charge`` column, not the trailing field.

    Raises:
        ValueError: *spectrum* is not in FragPipe's dotted four-field form.
    """
    parts = spectrum.split(".")
    if len(parts) < 4:
        raise ValueError(f"Unrecognized FragPipe Spectrum value: {spectrum!r}")
    file_name = parts[0].split("_sub")[0]
    scan_num = str(int(parts[1]))
    return f"{file_name}:{scan_num}:{charge}"


def extract_psm(psm_path: Path, output_path: Path) -> None:
    """Extract ``peptide<TAB>spectrum_title`` rows from FragPipe psm.tsv.

    One row is written per PSM with ``Intensity > 0``; duplicates are kept, as
    in the reference implementation.  Rows with a malformed ``Spectrum`` value
    or a non-numeric ``Intensity`` are skipped.
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
            except (ValueError, KeyError, TypeError):
                continue
            if intensity <= 0:
                continue
            try:
                title = _spectrum_to_title(row["Spectrum"], row["Charge"])
            except (ValueError, KeyError, TypeError):
                continue
            writer.writerow([row["Peptide"], title])
