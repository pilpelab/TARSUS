"""Step 8: Reference validation preparation — expand MGF with modification states.

Reads the SAAV table (subs.ipc), expands each spectrum entry over all
combinations of Met oxidation and Cys carbamidomethylation, patches
PEPMASS values with theoretical m/z, and generates chunked inputs for
PepQuery base rescoring.
"""

from itertools import product
from pathlib import Path
from typing import TextIO
import polars as pl

AA_MONO: dict[str, float] = {
    "A": 71.03711, "R": 156.10111, "N": 114.04293, "D": 115.02694,
    "C": 103.00919, "E": 129.04259, "Q": 128.05858, "G": 57.02146,
    "H": 137.05891, "I": 113.08406, "L": 113.08406, "K": 128.09496,
    "M": 131.04049, "F": 147.06841, "P": 97.05276, "S": 87.03203,
    "T": 101.04768, "W": 186.07931, "Y": 163.06333, "V": 99.06841,
}

WATER_MASS = 18.01056
OX_MASS = 15.994915
CAM_MASS = 57.021464
PROTON_MASS = 1.007276466812


def peptide_mz_all_states(seq: str, charge: int) -> dict[str, float]:
    """Calculate monoisotopic m/z for all modification state combinations.

    Modification states:
      - Met (M): unoxidized (0) or oxidized (+OX_MASS)
      - Cys (C): unmodified (0) or carbamidomethylated (+CAM_MASS)

    Returns dict mapping state key (e.g. 'M0C0', 'M3C1', 'M3_7C1_5') to m/z.
    """
    if charge <= 0:
        raise ValueError("Charge must be a positive integer")

    try:
        base_neutral = WATER_MASS + sum(AA_MONO[aa] for aa in seq)
    except KeyError as e:
        raise ValueError(f"Unknown amino acid: {e.args[0]}")

    m_positions = [i for i, aa in enumerate(seq) if aa == "M"]
    c_positions = [i for i, aa in enumerate(seq) if aa == "C"]

    result: dict[str, float] = {}
    for m_state in product([0, 1], repeat=len(m_positions)):
        for c_state in product([0, 1], repeat=len(c_positions)):
            neutral_mass = base_neutral
            neutral_mass += sum(s * OX_MASS for s in m_state)
            neutral_mass += sum(s * CAM_MASS for s in c_state)

            ox_pos = [m_positions[i] + 1 for i, s in enumerate(m_state) if s]
            cam_pos = [c_positions[i] + 1 for i, s in enumerate(c_state) if s]

            m_part = "M" + "_".join(str(p) for p in ox_pos) if ox_pos else "M0"
            c_part = "C" + "_".join(str(p) for p in cam_pos) if cam_pos else "C0"
            key = f"{m_part}{c_part}"

            result[key] = (neutral_mass + charge * PROTON_MASS) / charge

    return result


def mod_suffixes_for_seq(seq: str) -> list[str]:
    """Return all Cys/Met modification state suffixes for a peptide.

    e.g. ['M0C0', 'M3C1', 'M3_7C1_5']
    """
    m_positions = [i for i, aa in enumerate(seq) if aa == "M"]
    c_positions = [i for i, aa in enumerate(seq) if aa == "C"]

    if not m_positions and not c_positions:
        return ["M0C0"]

    suffixes: list[str] = []
    for m_state in product([0, 1], repeat=len(m_positions)):
        for c_state in product([0, 1], repeat=len(c_positions)):
            ox_pos = [m_positions[i] + 1 for i, s in enumerate(m_state) if s]
            cam_pos = [c_positions[i] + 1 for i, s in enumerate(c_state) if s]

            m_part = "M" + "_".join(str(p) for p in ox_pos) if ox_pos else "M0"
            c_part = "C" + "_".join(str(p) for p in cam_pos) if cam_pos else "C0"
            suffixes.append(f"{m_part}{c_part}")

    return suffixes


def _canon_title(t: str, use_base: bool) -> str:
    """Normalize spectrum titles for matching."""
    t = t.strip()
    if use_base and ":" in t:
        return t.rsplit(":", 1)[0]
    return t


def expand_mgf_with_mod_states(
    df: pl.DataFrame,
    mgf_in_path: Path,
    mgf_out_path: Path,
    use_base_title: bool = False,
    debug_unmatched: bool = True,
) -> None:
    """Stream through an MGF, expanding matched spectra with mod-state variants.

    For each spectrum in the MGF whose TITLE matches a row in *df*, the function
    patches PEPMASS to the theoretical m/z for each modification state and
    patches TITLE with the modification state suffix.

    Args:
        df: Must have columns 'Spectrum' and 'base' (peptide sequence).
        mgf_in_path: Input MGF file.
        mgf_out_path: Output MGF file with expanded mod-state variants.
        use_base_title: If True, strip trailing ':.*' from titles for matching.
        debug_unmatched: If True, print match statistics.
    """
    if not {"Spectrum", "base"}.issubset(df.columns):
        raise ValueError("DataFrame must have 'Spectrum' and 'base' columns.")

    title_to_peps: dict[str, list[str]] = {}
    for row in df.iter_rows(named=True):
        key = str(row["Spectrum"]).strip()
        title_to_peps.setdefault(key, []).append(str(row["base"]))

    wanted_titles = set(title_to_peps.keys())
    matched_titles: set[str] = set()
    charge_missing_for: set[str] = set()

    mgf_out_path.parent.mkdir(parents=True, exist_ok=True)
    with mgf_in_path.open("r") as fin, mgf_out_path.open("w") as fout:
        in_block = False
        block_lines: list[str] = []
        current_title_raw: str | None = None
        current_title_key: str | None = None
        pepmass_idx: int | None = None
        title_idx: int | None = None
        charge: int | None = None

        for line in fin:
            stripped = line.strip()

            if not in_block:
                if stripped == "BEGIN IONS":
                    in_block = True
                    block_lines = [line]
                    current_title_raw = None
                    current_title_key = None
                    pepmass_idx = None
                    title_idx = None
                    charge = None
                continue

            block_lines.append(line)

            if stripped.startswith("TITLE="):
                current_title_raw = stripped[len("TITLE="):].strip()
                current_title_key = _canon_title(
                    current_title_raw, use_base=use_base_title,
                )
                title_idx = len(block_lines) - 1

            elif stripped.startswith("PEPMASS="):
                pepmass_idx = len(block_lines) - 1

            elif stripped.startswith("CHARGE="):
                charge_str = stripped.split("=", 1)[1].strip().rstrip("+")
                try:
                    charge = int(charge_str)
                except ValueError:
                    charge = None

            elif stripped == "END IONS":
                if current_title_key in wanted_titles:
                    pass  # matched via normalized key
                elif current_title_raw in wanted_titles:
                    current_title_key = current_title_raw
                else:
                    current_title_key = None

                if current_title_key in wanted_titles:
                    if charge is None:
                        charge_missing_for.add(current_title_key)
                    elif pepmass_idx is not None and title_idx is not None:
                        matched_titles.add(current_title_key)
                        for pep in title_to_peps[current_title_key]:
                            mod_mz_dict = peptide_mz_all_states(pep, charge)
                            raw_title = current_title_raw or ""
                            base_title = (
                                _canon_title(raw_title, use_base=True)
                                if use_base_title
                                else raw_title
                            )
                            for mod_str, theo_mz in mod_mz_dict.items():
                                new_block = list(block_lines)
                                new_block[title_idx] = f"TITLE={base_title}_{mod_str}\n"
                                new_block[pepmass_idx] = f"PEPMASS={theo_mz:.6f}\n"
                                fout.writelines(new_block)

                in_block = False
                block_lines = []
                current_title_raw = None
                current_title_key = None
                pepmass_idx = None
                title_idx = None
                charge = None

    if debug_unmatched:
        unmatched = wanted_titles - matched_titles
        print(f"Total DF titles: {len(wanted_titles)}")
        print(f"Matched in MGF: {len(matched_titles)}")
        print(f"Missing charge: {len(charge_missing_for)}")
        print(f"Not found in MGF (by key): {len(unmatched)}")
        if unmatched:
            print("Example unmatched titles (up to 10):")
            for t in list(unmatched)[:10]:
                print(" ", t)


def write_dep_spectrum_chunks(
    df: pl.DataFrame,
    lines_per_file: int,
    out_prefix: str = "variants",
    out_dir: Path = Path("."),
) -> None:
    """Split variant DataFrame into chunked text files for PepQuery input.

    Each line: <base_peptide>\t<spectrum_title>_<mod_suffix>

    Args:
        df: Must have columns 'base' and 'Spectrum'.
        lines_per_file: Max lines per chunk file.
        out_prefix: Prefix for output file names.
        out_dir: Output directory (created if needed).
    """
    if not {"base", "Spectrum"}.issubset(df.columns):
        raise ValueError("DataFrame must have 'base' and 'Spectrum' columns.")
    if lines_per_file <= 0:
        raise ValueError("lines_per_file must be positive")

    out_dir.mkdir(parents=True, exist_ok=True)
    file_index = 1
    line_count = 0
    out_f: TextIO | None = None

    def _open_new() -> TextIO:
        nonlocal file_index, line_count, out_f
        if out_f is not None:
            out_f.close()
        path = out_dir / f"{out_prefix}_{file_index}.txt"
        f_out = path.open("w")
        file_index += 1
        line_count = 0
        return f_out

    opened = False
    for row in df.iter_rows(named=True):
        pep = str(row["base"])
        spec = str(row["Spectrum"])
        suffixes = mod_suffixes_for_seq(pep)
        for suffix in suffixes:
            if not opened or line_count >= lines_per_file:
                out_f = _open_new()
                opened = True
            assert out_f is not None
            out_f.write(f"{pep}\t{spec}_{suffix}\n")
            line_count += 1

    if out_f is not None:
        out_f.close()


def prepare_base_rescoring(
    subs_ipc: Path,
    mgf_in: Path,
    mgf_out: Path,
    pepquery_input_dir: Path,
    chunk_size: int = 1,
) -> None:
    """Prepare reference validation input from SAAV table and MGF.

    Runs the full Step 8 pipeline: expand MGF with modification states
    and write chunked PepQuery input files.
    """
    subs = pl.read_ipc(subs_ipc)
    expand_mgf_with_mod_states(subs, mgf_in, mgf_out)
    write_dep_spectrum_chunks(
        subs, lines_per_file=chunk_size,
        out_prefix="variants", out_dir=pepquery_input_dir,
    )
