"""Step 11: PyAscore-based localization of amino acid substitutions.

Reads the SAAV table (subs.ipc) and PepQuery rescoring results, runs
PyAscore to localize each substitution to specific residue positions,
and produces the final localized SAAV table.
"""

import re
from pathlib import Path
from typing import Any
import numpy as np
import polars as pl
from pyteomics import mgf
from pyascore import PyAscore

AA_MONO: dict[str, float] = {
    "A": 71.03711, "R": 156.10111, "N": 114.04293, "D": 115.02694,
    "C": 103.00919, "E": 129.04259, "Q": 128.05858, "G": 57.02146,
    "H": 137.05891, "I": 113.08406, "L": 113.08406, "K": 128.09496,
    "M": 131.04049, "F": 147.06841, "P": 97.05276, "S": 87.03203,
    "T": 101.04768, "W": 186.07931, "Y": 163.06333, "V": 99.06841,
}

WATER_MASS = 18.01056
PROTON_MASS = 1.007276466812

SUBSTITUTION_SHIFTS: dict[str, dict[str, float]] = {
    aa_from: {
        aa_to: round(AA_MONO[aa_to] - AA_MONO[aa_from], 4)
        for aa_to in AA_MONO if aa_to != aa_from
    }
    for aa_from in AA_MONO
}

_MODIFIABLE = "ACDEFGHIKLMNPQRSTVWY"


def mz_diff(peptide: str, observed_mz: float, charge: int) -> tuple[float, float, float, float]:
    """Compare theoretical monoisotopic m/z with observed m/z.

    Returns (theoretical_mz, delta_da, delta_ppm, delta_neutral).
    """
    try:
        neutral_mass = WATER_MASS + sum(AA_MONO[aa] for aa in peptide)
    except KeyError as e:
        raise ValueError(f"Unknown amino acid in sequence: {e.args[0]}")

    theoretical_mz = (neutral_mass + charge * PROTON_MASS) / charge
    delta_mz = observed_mz - theoretical_mz
    delta_ppm = (delta_mz / theoretical_mz) * 1e6
    delta_neutral = delta_mz * charge
    return theoretical_mz, delta_mz, delta_ppm, delta_neutral


def ascore_to_probability(ascore: np.floating) -> float:
    """Convert PyAscore to error probability."""
    prob = float(10 ** (-ascore / 10))
    return prob


def get_var_mod_positions(
    best_seq: str,
    mod_mass: float,
    aux_mod_pos: np.ndarray,
    aux_mod_mass: np.ndarray,
    mass_tol: float,
) -> list[int]:
    """Find 1-based residue positions carrying a specific variable modification.

    Args:
        best_seq: Best sequence from PyAscore (may contain [mass] annotations).
        mod_mass: Mass of the variable modification to locate.
        aux_mod_pos: Positions of auxiliary modifications (0-based).
        aux_mod_mass: Masses of auxiliary modifications.
        mass_tol: Mass tolerance for matching.

    Returns:
        List of 1-based positions matching the variable modification.
    """
    static_mass: dict[int, float] = {}
    for pos, mass in zip(aux_mod_pos, aux_mod_mass):
        pos_int = int(pos)
        if pos_int < 0:
            continue
        static_mass[pos_int] = static_mass.get(pos_int, 0.0) + float(mass)

    positions: list[int] = []
    aa_pos = 0
    i = 0
    while i < len(best_seq):
        c = best_seq[i]
        if c.isalpha():
            aa_pos += 1
            if i + 1 < len(best_seq) and best_seq[i + 1] == "[":
                j = best_seq.find("]", i + 2)
                if j == -1:
                    raise ValueError("Unbalanced brackets in best_sequence")
                mass_start = i + 2 if best_seq[i + 2] in "+-" else i + 1
                mass_str = best_seq[mass_start:j]
                total_mass = float(mass_str)
                static = static_mass.get(aa_pos, 0.0)
                var_mass = total_mass - static
                if abs(var_mass - mod_mass) <= mass_tol:
                    positions.append(aa_pos)
                i = j + 1
            else:
                i += 1
        else:
            i += 1
    return positions


def _parse_aux_mods(modification: Any) -> tuple[np.ndarray, np.ndarray]:
    """Extract auxiliary modification positions and masses from a PepQuery string.

    ``'Oxidation of M@3[15.9949]'`` -> ``([3], [15.9949])``

    These are the *other* modifications carried by the peptide.  PyAscore needs
    them so it can subtract their mass contribution before deciding where the
    substitution sits; omitting them shifts fragment masses and mislocalizes.
    Non-string or unparseable values yield empty arrays.
    """
    if not isinstance(modification, str):
        return np.array([], dtype=np.uint32), np.array([], dtype=np.float32)
    positions = [int(p) for p in re.findall(r"@(\d+)", modification)]
    masses = [float(m) for m in re.findall(r"\[([\d.]+)\]", modification)]
    n = min(len(positions), len(masses))
    return (
        np.array(positions[:n], dtype=np.uint32),
        np.array(masses[:n], dtype=np.float32),
    )


def _expected_position(row: dict[str, Any]) -> int:
    """1-based peptide position of the substitution for *row*.

    ``subs.ipc`` stores ``mistranslated_pos`` 0-based (Step 3b names candidates
    ``<peptide>_<origin><0-based pos><dest>``), while PyAscore reports 1-based
    positions.  Raises ``KeyError`` if the column is absent rather than
    defaulting — a silent default of 0 makes ``expected_pos`` always 1, which
    Step 7's ``mistranslated_pos > 0`` filter can never satisfy, so Step 11
    would return zero rows on every run.
    """
    return int(row["mistranslated_pos"]) + 1


# Step 8 patches each fake spectrum's TITLE with a Met/Cys modification-state
# suffix: `_M<pos>[_<pos>...]C<pos>[_<pos>...]`, e.g. `_M0C0`, `_M0C1`,
# `_M6_14C0`.  Anchor on that exact grammar.  The reference strips it with
# `_[^_]*$`, which only removes the final `_<chunk>` and therefore mangles every
# multi-position suffix (`..._M6_14C0` -> `..._M6`).  Measured on the reference's
# own psmrankall_base.txt: 1,638 of 25,615 rows (6.4%) are mangled this way and
# silently lose their base comparison. See D-048.
_MOD_SUFFIX = re.compile(r"_M(?:\d+(?:_\d+)*)C(?:\d+(?:_\d+)*)$")


def _strip_mod_suffix(title: str) -> str:
    """Remove Step 8's Met/Cys modification-state suffix from a spectrum title."""
    return _MOD_SUFFIX.sub("", title)


def _read_psmrank(path: Path) -> pl.DataFrame:
    """Read a PepQuery psm_rank aggregate, tolerating its ragged rows.

    PepQuery 2.0.2 occasionally repeats a row's final four fields
    (``n_ptm``, ``confident``, ``ref_delta_score``, ``mod_delta_score``)
    verbatim, emitting a 26-field line against its own 22-column header — 4 of
    19,913 rows on the trial dataset.  Fields 1-22 are a complete, valid record,
    so the duplicated tail is dropped rather than aborting the read.
    """
    return pl.read_csv(path, separator="\t", truncate_ragged_lines=True)


def _nonbase_hits(deps: pl.DataFrame, base: pl.DataFrame) -> pl.DataFrame:
    """Keep variant PSMs that outscore the reference peptide on the same spectrum.

    Base titles carry Step 8's modification-state suffix and are normalized back
    before joining.  The join is an *inner* join, per the reference: a variant
    that was never rescored against its base peptide has no evidence of being
    better and is dropped, not admitted.
    """
    base = base.with_columns(
        pl.col("spectrum_title").map_elements(
            _strip_mod_suffix, return_dtype=pl.String,
        ),
    )
    base_max = base.group_by(["peptide", "spectrum_title"]).agg(
        pl.col("score").max().alias("score_base"),
    )
    return (
        deps.join(base_max, on="spectrum_title", how="inner", suffix="_base")
        .with_columns(
            (pl.col("score") - pl.col("score_base")).alias("delta_score"),
        )
        .filter(pl.col("delta_score") > 0)
    )


def localize_shift(
    candidates: pl.DataFrame,
    spectra_path: Path,
    precursor_tol: float = 0.05,
) -> list[str]:
    """Run PyAscore localization and return the confidently localized titles.

    Args:
        candidates: DataFrame with columns 'spectrum_title', 'base', 'origin',
            'destination', 'mistranslated_pos', 'modification'.
        spectra_path: Path to MGF file with spectra for localization.
        precursor_tol: Precursor m/z tolerance for PyAscore.

    Returns:
        Spectrum titles whose substitution localized to the expected position.
    """
    spectra = mgf.IndexedMGF(str(spectra_path))
    sure_spectra: list[str] = []

    for row in candidates.iter_rows(named=True):
        origin, dest = str(row["origin"]), str(row["destination"])
        if origin == dest:
            continue
        mod_mass = SUBSTITUTION_SHIFTS.get(origin, {}).get(dest)
        if mod_mass is None:
            continue

        spec = spectra.get_spectrum(str(row["spectrum_title"]))
        z = spec["params"].get("charge", [2])[0]
        aux_mod_pos, aux_mod_mass = _parse_aux_mods(row.get("modification"))

        asc = PyAscore(
            bin_size=100.0,
            n_top=10,
            mod_group=_MODIFIABLE,
            mod_mass=mod_mass,
            mz_error=precursor_tol,
            fragment_types="by",
        )
        asc.score(
            mz_arr=spec["m/z array"],
            int_arr=spec["intensity array"],
            peptide=str(row["base"]),
            n_of_mod=1,
            max_fragment_charge=z - 1,
            aux_mod_pos=aux_mod_pos,
            aux_mod_mass=aux_mod_mass,
        )

        best = asc.pep_scores[0]
        sig = best["signature"]
        modified_indices = np.where(sig == 1)[0]

        modifiable_positions = [
            i for i, aa in enumerate(str(row["base"]), start=1)
            if aa in _MODIFIABLE
        ]
        best_positions = [modifiable_positions[i] for i in modified_indices]

        if (
            len(best_positions) == 1
            and best_positions[0] == _expected_position(row)
            and asc.pep_scores[0]["weighted_score"]
            > asc.pep_scores[1]["weighted_score"]
        ):
            sure_spectra.append(str(row["spectrum_title"]))

    return sure_spectra


def _label_isobaric_il(localized: pl.DataFrame) -> pl.DataFrame:
    """Label the isobaric pair correctly — the pipeline's last act.

    Ile and Leu share a mass (113.08406 Da), but the two ends of a substitution are
    **not** equally ambiguous (D-065, Slava's correction of D-064):

    - **origin** is the residue *before* the error. It comes from the base peptide,
      which maps to the reference proteome, whose sequence is fixed by the genome
      codon (I = ATT/ATC/ATA, L = CTN/TTA/TTG). So the origin is **known** — it is
      literally ``base[mistranslated_pos]``, a definite ``I`` or ``L``.
    - **destination** is the *misincorporated* residue, seen only by MS mass. That is
      genuinely ``I/L`` — the mass cannot tell Ile from Leu, and a misincorporation is
      not on the genome to look up.

    So origin is recovered from ``base`` (authoritative — verified to match the
    header-derived origin on every non-I/L row across all runs), and only the
    destination collapses to ``I/L``.

    **This must run after :func:`localize_shift` and immediately before the write.**
    The ``/`` cannot exist upstream — it fails *silently* in two places if it does:

    - ``step07_analyze_outputs.py:327`` — the header regex ``_(\\w)(\\d+)(\\w)`` and
      ``\\w`` (``[A-Za-z0-9_]``) does **not** match ``/``; ``_T5I/L`` would yield
      destination ``"I"``, the ``L`` quietly dropped.
    - ``step11_localize.py:222`` — ``SUBSTITUTION_SHIFTS.get(origin, {}).get(dest)``
      returns ``None`` for ``I/L`` (``AA_MONO`` has no such key) → ``continue``:
      **every I/L row would vanish.**

    Both are the ``.get() -> None -> continue`` mode behind D-048/D-049/D-057. The
    mass lookup above ran on the *class* ``I`` (valid, and mass-correct since Ile and
    Leu share a mass); the real-residue label is applied only here. **Idempotent** —
    origin is recomputed from ``base`` regardless of its current value, so this is
    safe to re-apply to an already-labelled file.
    """
    return localized.with_columns(
        pl.col("base").str.slice(pl.col("mistranslated_pos"), 1).alias("origin"),
        pl.col("destination").replace({"I": "I/L"}),
    )


def localize(
    subs_ipc: Path,
    psmrankall_path: Path,
    psmrankall_base_path: Path,
    spectra_mgf: Path,
    output_ipc: Path,
    output_csv: Path | None = None,
    precursor_tol: float = 0.05,
) -> pl.DataFrame:
    """Run full Step 11: filter candidates and localize substitutions.

    Reads subs.ipc (Step 7 output), filters on PepQuery delta_score > 0,
    runs PyAscore localization, and writes the final table.
    """
    subs = pl.read_ipc(subs_ipc)

    deps = _read_psmrank(psmrankall_path)
    base = _read_psmrank(psmrankall_base_path)

    nonbase_hits = _nonbase_hits(deps, base)

    # Join on spectrum_title, not on peptide as the reference does: in targeted
    # mode subs.ipc's spectrum_title *is* the PepQuery title, so this keeps each
    # candidate bound to the spectrum it was identified on rather than borrowing
    # another spectrum's evidence for the same peptide (D-047).
    candidates = subs.join(
        nonbase_hits, on="spectrum_title", how="inner", suffix="_query",
    )

    sure_titles = localize_shift(candidates, spectra_mgf, precursor_tol)

    # Return subs.ipc's own schema, as the reference does — not the widened join.
    localized = subs.filter(pl.col("spectrum_title").is_in(sure_titles))

    localized = _label_isobaric_il(localized)

    output_ipc.parent.mkdir(parents=True, exist_ok=True)
    localized.write_ipc(output_ipc)

    if output_csv:
        localized.write_csv(output_csv)

    return localized
