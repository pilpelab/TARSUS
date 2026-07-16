"""Step 7: Analyze PepQuery validation outputs.

Reads PepQuery validation results and FragPipe search outputs, filters
confident SAAV PSMs, requires two-fragment coverage of the substitution
site, joins first/second pass searches, and calculates abundance ratios.
"""

import re
from pathlib import Path
from typing import Any
import numpy as np
import polars as pl

AA_MAP: dict[str, str] = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Xle": "I",
    "Leu": "I", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}


def extract_pdv_ions(ion_string: Any) -> list[str] | int:
    """Extract b/y ion labels from a PDV ion string.

    Input: '[b3, y4+++, b5]'
    Output: ['b3', 'y4', 'b5']
    Returns -1 if *ion_string* is not a string.
    """
    if not isinstance(ion_string, str):
        return -1
    items = ion_string.strip("[]").split(", ")
    values: list[str] = []
    for item in items:
        m = re.match(r"([by])(\d+)", item)
        if m:
            values.append(m.group(0))
    return sorted(set(values))


def _parse_modification(mod: str) -> dict[str, Any] | None:
    """Parse a PepQuery PTM modification string.

    'Ala->Gly@42[' -> {'origin': 'A', 'dest': 'G', 'position': 42}
    Returns None if the string does not match.
    """
    m = re.match(r"([A-Za-z]{3})->([A-Za-z]{3}).*@(\d+)\[", mod)
    if not m:
        return None
    origin_3 = m.group(1)
    dest_3 = m.group(2)
    origin = AA_MAP.get(origin_3, origin_3)
    dest = AA_MAP.get(dest_3, dest_3)
    return {"origin": origin, "dest": dest, "position": int(m.group(3))}


def _normalize_il(seq: str) -> str:
    """Replace I and L with J for I/L ambiguity correction."""
    return seq.replace("I", "J").replace("L", "J")


def load_ptm_details(ptmall_path: Path) -> pl.DataFrame:
    """Load PepQuery ptmall.txt and extract origin/dest/position."""
    # ptmall.txt is very large (9+ GB on the trial dataset), but Step 7 only
    # needs five columns for the single-SAV filter. Reading only those columns
    # avoids materializing the full PepQuery PTM table in memory.
    ptm = pl.read_csv(
        ptmall_path,
        separator="\t",
        has_header=False,
        columns=[0, 3, 19, 26, 27],
        new_columns=[
            "peptide", "spectrum_title", "ptm_peptide",
            "ptm_modification", "ptm_score",
        ],
        truncate_ragged_lines=True,
        ignore_errors=True,
    )

    parsed = ptm["ptm_modification"].map_elements(
        _parse_modification, return_dtype=pl.Struct(
            {"origin": pl.String, "dest": pl.String, "position": pl.Int64},
        ),
    )
    ptm = ptm.with_columns([
        parsed.struct.field("origin").alias("origin"),
        parsed.struct.field("dest").alias("dest"),
        (parsed.struct.field("position") - 1).alias("mistranslated_pos"),
    ])
    return ptm


def filter_single_sav_psms(ptm: pl.DataFrame) -> pl.DataFrame:
    """Keep PSMs unambiguously assigned to a single SAAV.

    Filters:
    - Only PSMs where ALL modifications contain '->' (valid SAAVs)
    - Valid position range
    - Creates modified_peptide by applying the substitution
    - I/L normalization
    - Keeps only PSMs where the modified sequence matches the base
    - Keeps only PSMs with exactly one unique SAV per spectrum
    """
    sav_spectra = ptm.group_by("spectrum_title").agg(
        pl.col("ptm_modification").str.contains("->").all(),
    ).filter(pl.col("ptm_modification"))
    ptm_subonly = ptm.filter(
        pl.col("spectrum_title").is_in(sav_spectra.get_column("spectrum_title").to_list()),
    )

    df_valid = ptm_subonly.filter(
        (pl.col("mistranslated_pos") >= 0)
        & (pl.col("mistranslated_pos") < pl.col("ptm_peptide").str.len_bytes()),
    )

    df_valid = df_valid.with_columns(
        (
            pl.col("ptm_peptide").str.slice(0, pl.col("mistranslated_pos"))
            + pl.col("dest")
            + pl.col("ptm_peptide").str.slice(pl.col("mistranslated_pos") + 1)
        ).alias("modified_peptide"),
    )

    df = df_valid.with_columns([
        pl.col("peptide").str.replace_all("I", "J", literal=True)
        .str.replace_all("L", "J", literal=True).alias("peptide_mod"),
        pl.col("modified_peptide").str.replace_all("I", "J", literal=True)
        .str.replace_all("L", "J", literal=True).alias("modified_peptide_mod"),
    ])

    group_stats = df.group_by("spectrum_title").agg([
        pl.col("ptm_score").max().alias("max_ptm_score"),
        pl.col("ptm_score").filter(
            pl.col("ptm_score") == pl.col("ptm_score").max(),
        ).count().alias("max_count"),
    ])
    second_max = df.group_by("spectrum_title").agg([
        pl.col("ptm_score").filter(
            pl.col("ptm_score") < pl.col("ptm_score").max(),
        ).max().alias("second_max_ptm_score"),
    ])
    df_merged = (
        df.join(group_stats, on="spectrum_title", how="left")
        .join(second_max, on="spectrum_title", how="left")
        .with_columns(pl.col("second_max_ptm_score").fill_null(1))
    )

    df_selected = df_merged.filter(
        (pl.col("max_count") == 1)
        & (pl.col("ptm_score") == pl.col("max_ptm_score")),
    )

    sure = df_selected.filter(
        pl.col("peptide_mod") == pl.col("modified_peptide_mod"),
    )

    sure = (
        sure.group_by("spectrum_title")
        .len()
        .filter(pl.col("len") == 1)
        .join(sure, on="spectrum_title")
    )
    return sure


def _compute_expected_ions(dependent: str, position: int) -> list[str]:
    """Generate expected b and y ions for a substitution at *position*."""
    n = len(dependent)
    ions: list[str] = []
    ions.extend(f"b{i}" for i in range(position + 1, n + 1))
    ions.extend(f"y{i}" for i in range(n - position + 2, n + 1))
    return ions


def _spectrum_to_title(spec: str) -> str:
    """Convert FragPipe Spectrum value to PepQuery/PDV spectrum_title.

    FragPipe writes ``file_sub.scan.scan.charge``.  Step 2 indexes the
    *original* mzML, so PepQuery/PDV titles are ``file:scan:charge`` with no
    ``_sub`` suffix — strip it here to land in that namespace, matching the
    reference ``analyze_outputs.py`` and Step 4's ``_spectrum_to_title``.

    See D-047 in ``.memory/decisions.md``.
    """
    parts = spec.split(".")
    file_name = parts[0].split("_sub")[0]
    scan_num = str(int(parts[1]))
    return f"{file_name}:{scan_num}:{parts[-1]}"


def _extract_base_name(protein: str) -> str:
    """Extract the base reference name from Protein field."""
    return protein.split("_")[0]


def analyze_outputs(
    first_psm_path: Path,
    second_psm_path: Path,
    ptmall_path: Path,
    psmrankall_path: Path,
    pdv_path: Path,
    output_ipc: Path,
) -> pl.DataFrame:
    """Analyze PepQuery validation outputs and produce SAAV table.

    Reads PepQuery results and FragPipe search outputs, filters confident
    SAAV candidates, and produces the subs.ipc table with abundance ratios.
    """
    # 1. Load PTM details from PepQuery
    ptm = load_ptm_details(ptmall_path)
    saved_singles = filter_single_sav_psms(ptm)
    saved_set: set[str] = set(saved_singles["spectrum_title"].to_list())

    # 2. Confident PepQuery hits
    # PepQuery 2.0.2 sometimes repeats a row's last four fields, giving a
    # 26-field line against its 22-column header. Fields 1-22 stay valid.
    first = pl.read_csv(
        psmrankall_path,
        separator="\t",
        columns=["spectrum_title", "confident"],
        truncate_ragged_lines=True,
    )
    first = first.filter(pl.col("confident") == "Yes")
    first_set: set[str] = set(first["spectrum_title"].to_list())

    # 3. PDV ion export: build {peptide: {spectrum_title: [ions]}}
    pdv_export: dict[str, dict[str, list[str]]] = {}
    try:
        pdv_df = pl.read_csv(
            pdv_path,
            separator="\t",
            columns=["Spectrum_Title", "peptide", "ions"],
        )
        for row in pdv_df.iter_rows(named=True):
            pep_key = str(row.get("peptide", ""))
            spec_key = str(row.get("Spectrum_Title", ""))
            ions = extract_pdv_ions(str(row.get("ions", "")))
            if isinstance(ions, list):
                pdv_export.setdefault(pep_key, {})[spec_key] = ions
    except Exception:
        pass

    # 4. First-pass PSMs (reference search)
    first_psms = pl.read_csv(first_psm_path, separator="\t")
    first_psms = first_psms.rename({"Intensity": "first_intensity"})
    first_psms = first_psms.rename({"Peptide": "base"})
    first_psms = first_psms.filter(pl.col("first_intensity") > 0)
    first_psms = first_psms.with_columns([
        pl.max("first_intensity").over("base", "Charge").alias("intensity_max"),
    ])
    first_psms = first_psms.filter(
        pl.col("first_intensity") == pl.col("intensity_max"),
    ).drop("intensity_max")

    # 5. Second-pass PSMs (variant search)
    second_all = pl.read_csv(second_psm_path, separator="\t")
    second_all = second_all.rename({"Peptide": "dependent", "Intensity": "second_intensity"})
    second_all = second_all.filter(pl.col("second_intensity") > 0)
    second_all = second_all.with_columns(
        pl.col("Protein").map_elements(_extract_base_name, return_dtype=pl.String).alias("base"),
    )

    # Convert Spectrum to canonical title
    titles = second_all["Spectrum"].map_elements(
        _spectrum_to_title, return_dtype=pl.String,
    ).alias("spectrum_title")
    second_all = second_all.with_columns(titles)

    second_psms = second_all.filter(
        pl.col("spectrum_title").is_in(first_set | saved_set),
    )

    # 6. Expected ion series for each candidate
    unique_deps = second_psms.select(["dependent", "Protein"]).unique()
    expected: dict[str, list[str]] = {}
    for row in unique_deps.iter_rows(named=True):
        dep = str(row["dependent"])
        pos_match = re.search(r"\D(\d+)\D*$", str(row.get("Protein", "")))
        if pos_match:
            pos = int(pos_match.group(1))
            ions = _compute_expected_ions(dep, pos)
            expected[dep] = ions

    # 7. Two-fragment coverage filter
    two_fragment_psms: list[str] = []
    for dep, ions in expected.items():
        pdv_pep = pdv_export.get(dep, {})
        for spec, observed in pdv_pep.items():
            if len(set(observed) & set(ions)) > 1:
                two_fragment_psms.append(spec)

    second_psms = second_psms.filter(
        pl.col("spectrum_title").is_in(two_fragment_psms),
    )

    # 8. Max intensity per dependent+Charge
    second_psms = second_psms.with_columns([
        pl.max("second_intensity").over("dependent", "Charge").alias("intensity_max"),
    ])
    second_psms = second_psms.filter(
        pl.col("second_intensity") == pl.col("intensity_max"),
    ).drop("intensity_max")

    # 9. Join first and second pass
    join_cols = ["base", "Charge"]
    # Ensure both have needed columns
    for c in join_cols:
        if c not in second_psms.columns:
            pass

    first_sub = first_psms.select([
        "Spectrum", "base", "Prev AA", "Next AA", "Protein",
        "first_intensity", "Retention", "Charge", "Protein Start",
        "Protein End", "Mapped Proteins", "Hyperscore",
        "Extended Peptide", "Number of Missed Cleavages", "Is Unique",
    ])

    joined = second_psms.join(first_sub, on=join_cols, suffix="_first")

    # 10. Extract substitution position from Protein field
    pos_pattern = r"_(?:\D*)(\d+)"
    joined = joined.with_columns(
        pl.col("Protein").str.extract(pos_pattern, 1)
        .cast(pl.Int64).alias("mistranslated_pos"),
    ).filter(pl.col("mistranslated_pos") > 0)

    # 11. Extract origin, destination, protein position.
    #
    # ORIGIN is read from `base`, NOT from the candidate header. The header carries
    # the collapsed class letter `I` for the whole isobaric pair (Step 3b), so taking
    # origin from it would mislabel every LEUCINE origin as `I`. But the origin is
    # known: it is the reference residue at the substituted position, and the genome
    # codon spells out I vs L. `base[mistranslated_pos]` is authoritative — there is
    # no such thing as an ambiguous `I/L` origin (D-065).
    #
    # DESTINATION stays the header's class letter `I` here; it is the misincorporated
    # residue, seen only by mass, so it is genuinely ambiguous. Step 11 relabels it
    # `I/L` as its last act — the `/` must not enter the mass lookup before then.
    sub_pattern = r"_(\w)(\d+)(\w)"
    joined = joined.with_columns([
        pl.col("base").str.slice(pl.col("mistranslated_pos"), 1).alias("origin"),
        pl.col("Protein").str.extract(sub_pattern, 3).alias("destination"),
        (
            pl.col("Protein Start_first") + pl.col("mistranslated_pos") - 1
        ).alias("misProt"),
    ])

    # 12. Abundance ratio
    ratio = (
        np.log10(
            joined["second_intensity"].to_numpy()
            / joined["first_intensity"].to_numpy(),
        )
    )
    joined = joined.with_columns(pl.Series("dpbp", ratio))

    output_ipc.parent.mkdir(parents=True, exist_ok=True)
    joined.write_ipc(output_ipc)
    return joined
