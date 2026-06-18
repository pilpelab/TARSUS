"""Step 11: PyAscore-based localization of amino acid substitutions.

Reads the SAAV table (subs.ipc) and PepQuery rescoring results, runs
PyAscore to localize each substitution to specific residue positions,
and produces the final localized SAAV table.
"""

from pathlib import Path
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


def localize_shift(
    candidates: pl.DataFrame,
    spectra_path: Path,
    precursor_tol: float = 0.05,
) -> pl.DataFrame:
    """Run PyAscore localization on substitution candidates.

    Args:
        candidates: DataFrame with columns including 'spectrum_title', 'base',
            'dependent', 'origin', 'destination', 'mistranslatedPos'.
        spectra_path: Path to MGF file with spectra for localization.
        precursor_tol: Precursor m/z tolerance for PyAscore.

    Returns:
        DataFrame filtered to confidently localized substitutions.
    """
    spectra = mgf.IndexedMGF(str(spectra_path))
    sure_spectra: list[str] = []

    for row in candidates.iter_rows(named=True):
        mod_mass = SUBSTITUTION_SHIFTS.get(
            str(row.get("origin", "")), {},
        ).get(str(row.get("destination", "")), 0.0)

        if mod_mass == 0.0 and row.get("origin") != row.get("destination"):
            continue

        spec = spectra.get_spectrum(str(row["spectrum_title"]))
        z = spec["params"].get("charge", [2])[0]

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
            aux_mod_pos=np.array([], dtype=np.uint32),
            aux_mod_mass=np.array([], dtype=np.float32),
        )

        best = asc.pep_scores[0]
        sig = best["signature"]
        modified_indices = np.where(sig == 1)[0]

        modifiable_positions = [
            i for i, aa in enumerate(str(row["base"]), start=1)
            if aa in _MODIFIABLE
        ]
        best_positions = [modifiable_positions[i] for i in modified_indices]

        expected_pos = int(row.get("mistranslatedPos", 0)) + 1
        if (
            len(best_positions) == 1
            and best_positions[0] == expected_pos
            and asc.pep_scores[0]["weighted_score"]
            > asc.pep_scores[1]["weighted_score"]
        ):
            sure_spectra.append(str(row["spectrum_title"]))

    result = candidates.filter(
        pl.col("spectrum_title").is_in(sure_spectra),
    )
    return result


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

    deps = pl.read_csv(psmrankall_path, separator="\t")
    base = pl.read_csv(psmrankall_base_path, separator="\t").with_columns(
        pl.col("spectrum_title").str.replace(r"_[^_]*$", ""),
    )

    base_max = base.group_by(["peptide", "spectrum_title"]).agg(
        pl.col("score").max().alias("score_max"),
    )
    nonbase_hits = deps.join(
        base_max, on=["spectrum_title"], how="left",
    ).with_columns(
        (pl.col("score") - pl.col("score_max").fill_null(0)).alias("delta_score"),
    ).filter(pl.col("delta_score") > 0)

    candidates = subs.join(
        nonbase_hits, on="spectrum_title", how="inner", suffix="_query",
    )

    localized = localize_shift(candidates, spectra_mgf, precursor_tol)

    output_ipc.parent.mkdir(parents=True, exist_ok=True)
    localized.write_ipc(output_ipc)

    if output_csv:
        localized.write_csv(output_csv)

    return localized
