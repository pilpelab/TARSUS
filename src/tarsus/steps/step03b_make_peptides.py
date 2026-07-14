"""Step 3b: In-silico mutagenesis — generate variant peptide candidates.

Reads the FragPipe first-pass peptide identifications and the substitution
exclusion matrix, then generates all allowed single-amino-acid variant
peptides not already observed in the data.
"""

import re
from pathlib import Path
import polars as pl
from ..assets import SUBS_EXCLUDE_CSV


def _norm_aa(aa: str) -> str:
    """Normalize an amino-acid label; the CSV's 'I/L' means 'I'."""
    aa = aa.strip()
    return "I" if aa == "I/L" else aa


def _load_substitution_matrix(path: Path) -> dict[str, dict[str, bool]]:
    """Load the substitution exclusion matrix as ``{origin: {dest: excluded}}``.

    **The CSV is COLUMN=origin, ROW=destination.** The reference README says so
    outright — *"Columns are origin amino acids, rows are destination amino acids.
    True value excludes origin->destination mutation"* — and its ``make_peptides.py``
    relies on it: ``pd.read_csv(...).to_dict()`` yields ``{COLUMN: {ROW: value}}``,
    which it then indexes as ``subs_allowed[origin][dest]``.

    We previously built ``matrix[ROW][COLUMN]`` — i.e. ``matrix[dest][origin]`` —
    and used it as ``matrix[origin][dest]``, **transposing every one of the 20
    asymmetric pairs**. On real data that meant:

    - **F→M**: excluded by the reference (an oxidised-Met artifact — Phe is only
      0.033 Da from Met+oxidation). We generated **15,004 candidates**, and it
      became our single largest "finding" (38 of 248 localized = 15%).
    - **T→S**: allowed by the reference and its *dominant* substitution
      (**422 of 697 localized = 61%**). We generated **zero**. We were
      structurally incapable of finding it.

    See D-061.
    """
    raw = pl.read_csv(path, has_header=True)
    header = [c.strip() for c in raw.columns]
    label_col = header[0]

    matrix: dict[str, dict[str, bool]] = {}
    for row in raw.iter_rows(named=True):
        dest = _norm_aa(str(row[label_col]))            # ROW label = DESTINATION
        for col, val in row.items():
            if col.strip() == label_col or not col.strip():
                continue
            origin = _norm_aa(col)                      # COLUMN name = ORIGIN
            excluded = str(val).strip().upper() == "TRUE"
            matrix.setdefault(origin, {})[dest] = excluded
    return matrix


#: Substitutions the reference's own results prove must be present in any healthy
#: library. T->S is its DOMINANT substitution — 422 of its 697 localized SAAVs
#: (61%). D-061's transposed matrix made it zero, and nothing noticed for weeks.
REQUIRED_SUBSTITUTIONS: set[tuple[str, str]] = {("T", "S")}


def check_library_spectrum(
    fasta: Path,
    matrix: dict[str, dict[str, bool]],
    required: set[tuple[str, str]] | None = None,
) -> dict[tuple[str, str], int]:
    """Validate the candidate library's substitution spectrum. Raise if it is wrong.

    **Step 3b decides the entire search space.** A substitution absent from the
    library can never be found by *any* downstream step — and nothing anywhere
    reports its absence. That silence has invalidated every result in this project
    twice:

    - **D-057:** the library was built 76 minutes *before* its own I/L fix, so it
      held **0 of 7.37M** ``->Ile`` variants. Two weeks of results were computed
      against a search space that could not contain the answer.
    - **D-061:** the exclusion matrix was read transposed, so **F->M** (an
      oxidised-Met artifact the reference excludes — Phe is only 0.033 Da from
      Met+oxidation) got 15,004 candidates and became our single largest
      "finding", while **T->S** (the reference's dominant substitution) got zero.

    Both were silent. This guard makes them loud.

    Args:
        fasta: the written ``pep_candidates.fa``.
        matrix: ``{origin: {dest: excluded}}`` from :func:`_load_substitution_matrix`.
        required: substitutions that must be non-empty. Defaults to
            :data:`REQUIRED_SUBSTITUTIONS`.

    Returns:
        The observed spectrum, ``{(origin, dest): count}``.

    Raises:
        RuntimeError: an excluded substitution was generated, or a required one is
            missing.
    """
    if required is None:
        required = REQUIRED_SUBSTITUTIONS

    spectrum: dict[tuple[str, str], int] = {}
    header_re = re.compile(r"^>.*_([A-Z])(\d+)([A-Z])$")
    with fasta.open() as f:
        for line in f:
            if not line.startswith(">"):
                continue
            m = header_re.match(line.strip())
            if m:
                key = (m.group(1), m.group(3))
                spectrum[key] = spectrum.get(key, 0) + 1

    forbidden = sorted(
        f"{o}->{d} ({n:,} candidates)"
        for (o, d), n in spectrum.items()
        if n and matrix.get(o, {}).get(d, False)
    )
    if forbidden:
        raise RuntimeError(
            f"Step 3b generated substitutions the exclusion matrix forbids: "
            f"{', '.join(forbidden)}. The candidate library is wrong — every "
            f"downstream result would be polluted by artifacts. This is the D-061 "
            f"signature (a transposed matrix put 15,004 F->M artifacts in the "
            f"library and made them our largest 'finding'). Check "
            f"`_load_substitution_matrix`: the CSV is COLUMN=origin, ROW=destination."
        )

    missing = sorted(f"{o}->{d}" for (o, d) in required if not spectrum.get((o, d)))
    if missing:
        raise RuntimeError(
            f"Step 3b produced NO candidates for: {', '.join(missing)}. These are "
            f"substitutions the reference finds in abundance — T->S alone is 422 of "
            f"its 697 localized SAAVs (61%). A substitution absent from the library "
            f"can never be found by any downstream step, and nothing else would "
            f"report it. This is the D-057/D-061 signature."
        )
    return spectrum


def _single_substitutions(
    peptide: str, origin: str, dest: str,
) -> list[tuple[str, int]]:
    """Generate all single-AA substitutions in *peptide*.

    Canonicalizes I/L to I — mass spec cannot distinguish isoleucine
    from leucine (identical mass 113.08406 Da).  The FASTA header
    retains "I/L" notation for informational purposes.

    Returns list of (variant_sequence, position).
    """
    if dest == "I/L":
        dest = "I"
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

    # The search space is now fixed. Verify it before anything downstream can
    # silently inherit a wrong one — this is the check that would have caught both
    # D-057 and D-061 on day one.
    #
    # Only require a substitution whose ORIGIN residue actually occurs in the
    # observed peptides and which the matrix allows: absence is a bug only when the
    # library *could* have contained it.
    required = {
        (o, d) for (o, d) in REQUIRED_SUBSTITUTIONS
        if not matrix.get(o, {}).get(d, True)
        and any(o in pep for pep in observed)
    }
    spectrum = check_library_spectrum(output_fasta, matrix, required=required)
    top = sorted(spectrum.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print(f"[step03b] candidate library: {sum(spectrum.values()):,} variants")
    print("[step03b] top substitution classes: " + ", ".join(
        f"{o}->{d} {n:,}" for (o, d), n in top
    ))
