"""Step 3b: In-silico mutagenesis — generate variant peptide candidates.

Reads the FragPipe first-pass peptide identifications and the substitution
exclusion matrix, then generates all allowed single-amino-acid variant
peptides not already observed in the data.
"""

from pathlib import Path
import polars as pl
from ..assets import SUBS_EXCLUDE_CSV


def _load_substitution_matrix(path: Path) -> dict[str, dict[str, bool]]:
    """Load the substitution exclusion matrix.

    Returns {origin_aa: {dest_aa: excluded_bool}}.
    The CSV column 'I/L' is normalized to 'I'.
    """
    raw = pl.read_csv(path, has_header=True)
    cols = raw.columns
    header = [c.strip() for c in cols]
    matrix: dict[str, dict[str, bool]] = {}
    for row in raw.iter_rows(named=True):
        origin = str(row[header[0]]).strip()
        if origin in ("I/L",):
            origin = "I"
        dest_map: dict[str, bool] = {}
        for col, val in row.items():
            col_name = col.strip()
            if col_name == header[0] or col_name in ("",):
                continue
            dest_map[col_name] = str(val).strip().upper() == "TRUE"
        matrix[origin] = dest_map
    return matrix


def _single_substitutions(
    peptide: str, origin: str, dest: str,
) -> list[tuple[str, int]]:
    """Generate all single-AA substitutions in *peptide*.

    Returns list of (variant_sequence, position).
    """
    results: list[tuple[str, int]] = []
    for i, char in enumerate(peptide):
        if char == origin:
            variant = peptide[:i] + dest + peptide[i + 1:]
            results.append((variant, i))
    return results


def make_peptide_candidates(
    peptide_tsv: Path,
    substitution_matrix: Path | None = None,
    output_fasta: Path | None = None,
) -> None:
    """Generate candidate variant peptides and write a FASTA file.

    Args:
        peptide_tsv: FragPipe first-pass peptide.tsv (tab-separated).
        substitution_matrix: CSV with substitution exclusion rules.
            Defaults to the bundled subs_exclude.csv.
        output_fasta: Output FASTA path (e.g. pep_candidates.fa).
    """
    if substitution_matrix is None:
        substitution_matrix = SUBS_EXCLUDE_CSV
    if output_fasta is None:
        output_fasta = peptide_tsv.parent / "pep_candidates.fa"
    matrix = _load_substitution_matrix(substitution_matrix)

    peptides = pl.read_csv(
        peptide_tsv, separator="\t", null_values=["NA", ""],
    )
    if peptides.is_empty():
        output_fasta.parent.mkdir(parents=True, exist_ok=True)
        output_fasta.touch()
        return
    peptides = peptides.filter(pl.col("Intensity") > 0)
    observed: set[str] = set(peptides["Peptide"].unique())

    output_fasta.parent.mkdir(parents=True, exist_ok=True)
    with output_fasta.open("w") as f:
        for pep in sorted(observed):
            for origin, dest_map in matrix.items():
                for dest, excluded in dest_map.items():
                    if excluded or origin == dest:
                        continue
                    if origin not in pep:
                        continue
                    for var, pos in _single_substitutions(pep, origin, dest):
                        if var in observed:
                            continue
                        header = f">{pep}_{origin}{pos}{dest}"
                        f.write(f"{header}\n{var}\n")
