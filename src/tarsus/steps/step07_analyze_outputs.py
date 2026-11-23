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

    The search is UNANCHORED, matching the reference's polars ``str.extract``.
    A substitution is rarely the first modification listed — PepQuery writes the
    fixed/variable mods first::

        'Carbamidomethylation of C@5[57.0215];Gly->Ala of G@3[14.0157]'

    ``re.match`` anchors at position 0 and returns None for every one of those,
    which silently dropped essentially every Cys- (carbamidomethyl) and Met-
    (oxidation) containing PSM — 0/201 parsed on the affected rows, vs 201/201
    once unanchored. That is a chemically biased loss, not a uniform one, and it
    skewed the substitution spectrum against the reference (D-070).

    ``.*`` stays greedy so the trailing ``@(\\d+)[`` binds to the last modification
    on the line, exactly as the reference's regex does.
    """
    m = re.search(r"([A-Za-z]{3})->([A-Za-z]{3}).*@(\d+)\[", mod)
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
        (parsed.struct.field("position") - 1).alias("mistranslatedPos"),
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
        (pl.col("mistranslatedPos") >= 0)
        & (pl.col("mistranslatedPos") < pl.col("ptm_peptide").str.len_bytes()),
    )

    df_valid = df_valid.with_columns(
        (
            pl.col("ptm_peptide").str.slice(0, pl.col("mistranslatedPos"))
            + pl.col("dest")
            + pl.col("ptm_peptide").str.slice(pl.col("mistranslatedPos") + 1)
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
    """Every b and y ion that contains the substituted residue at *position*.

    *position* is 0-based (Step 3b's header carries ``enumerate`` indices). b_k
    holds residues 0..k-1, so it contains the residue for k >= position + 1. y_k
    holds the last k residues, so it contains it for k >= n - position. Only these
    ions carry the substitution's mass shift, which is what the two-fragment filter
    needs.

    The reference ``analyze_outputs.py`` (and this step until D-078) started the y
    ions at n - position + 2, against its own docstring ("from
    len(dependent)-position"). That dropped the two shortest containing y ions,
    often the clearest peaks, and left substitutions at positions 0 and 1 with no
    y ion at all. Measured on the four D-073 runs: 77 of 970 Step 7 spectra (8%)
    were removed by it, none admitted.
    """
    n = len(dependent)
    ions: list[str] = []
    ions.extend(f"b{i}" for i in range(position + 1, n + 1))
    ions.extend(f"y{i}" for i in range(n - position, n + 1))
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


def _drop_decoy_rows(df: pl.DataFrame) -> pl.DataFrame:
    """Drop rows anchored on a reverse-decoy protein (``rev_`` prefix).

    A first-pass PSM whose protein is a reverse decoy (``rev_`` prefix, generated
    in step03a/step03c) is an FDR artifact, not a real reference peptide — its
    ``first Intensity`` would be a bogus ``dpbp`` denominator. The reference
    ``analyze_outputs.py`` omits this filter and got 0 decoys by luck; we get 1-8
    per run (Slava's ``subs.ipc`` has 0). ``rev_`` never prefixes a real variant
    id, so this cannot drop a genuine detection. See lessons 2026-07-27.
    """
    cols = [c for c in ("Protein", "Protein_right") if c in df.columns]
    if not cols:
        return df
    is_decoy = pl.any_horizontal(
        [pl.col(c).cast(pl.Utf8).str.starts_with("rev_") for c in cols]
    )
    return df.filter(~is_decoy)


def analyze_outputs(
    first_psm_path: Path,
    second_psm_path: Path,
    ptmall_path: Path,
    psmrankall_path: Path,
    pdv_path: Path,
    output_ipc: Path,
    sample: str | None = None,
) -> pl.DataFrame:
    """Analyze PepQuery validation outputs and produce SAAV table.

    Reads PepQuery results and FragPipe search outputs, filters confident
    SAAV candidates, and produces the subs.ipc table with abundance ratios.

    *sample* labels which run each row came from, so several runs can be
    concatenated and still be told apart — the reference takes it from the run
    directory name. Defaults to the run directory inferred from *output_ipc*
    (``<run>/07_analyze/subs.ipc`` -> ``<run>``).
    """
    if sample is None:
        sample = output_ipc.parent.parent.name
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

    # 3. PDV ion export: build {peptide: {spectrum_title: [ions]}} for the
    #    two-fragment filter, and keep the raw annotation columns for the table.
    #
    #    PDV writes `ions`/`ions_mz`/`ions_int` as bracketed strings; Slava's
    #    GAPDH subs.ipc carries them verbatim (String dtype) under the names
    #    `ions`/`ion_mz`/`ion_int`, sitting right after `Traced Scans`.
    pdv_export: dict[str, dict[str, list[str]]] = {}
    pdv_ions: pl.DataFrame | None = None
    try:
        pdv_df = pl.read_csv(
            pdv_path,
            separator="\t",
            columns=["Spectrum_Title", "peptide", "ions", "ions_mz", "ions_int"],
        )
        for row in pdv_df.iter_rows(named=True):
            pep_key = str(row.get("peptide", ""))
            spec_key = str(row.get("Spectrum_Title", ""))
            ions = extract_pdv_ions(str(row.get("ions", "")))
            if isinstance(ions, list):
                pdv_export.setdefault(pep_key, {})[spec_key] = ions

        # One annotation row per (spectrum, peptide) — PDV can repeat a pair, and
        # a duplicated right side would multiply rows in the join below.
        pdv_ions = pdv_df.rename({
            "Spectrum_Title": "spectrum_title",
            "peptide": "dependent",
            "ions_mz": "ion_mz",
            "ions_int": "ion_int",
        }).unique(subset=["spectrum_title", "dependent"], keep="first")
    except Exception:
        pass

    # 4. First-pass PSMs (reference search)
    first_psms = pl.read_csv(first_psm_path, separator="\t")
    first_psms = first_psms.rename({"Intensity": "first Intensity"})
    first_psms = first_psms.rename({"Peptide": "base"})
    first_psms = first_psms.filter(pl.col("first Intensity") > 0)
    first_psms = first_psms.with_columns([
        pl.max("first Intensity").over("base", "Charge").alias("intensity_max"),
    ])
    first_psms = first_psms.filter(
        pl.col("first Intensity") == pl.col("intensity_max"),
    ).drop("intensity_max")

    # 5. Second-pass PSMs (variant search)
    second_all = pl.read_csv(second_psm_path, separator="\t")
    second_all = second_all.rename({"Peptide": "dependent", "Intensity": "second Intensity"})
    second_all = second_all.filter(pl.col("second Intensity") > 0)
    second_all = second_all.with_columns(
        pl.col("Protein").map_elements(_extract_base_name, return_dtype=pl.String).alias("base"),
        pl.lit(sample).alias("sample"),
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
        pl.max("second Intensity").over("dependent", "Charge").alias("intensity_max"),
    ])
    second_psms = second_psms.filter(
        pl.col("second Intensity") == pl.col("intensity_max"),
    ).drop("intensity_max")

    # 8b. Attach the PDV fragment annotation (`ions`/`ion_mz`/`ion_int`).
    #
    # Left join: every surviving row already passed the two-fragment filter, so a
    # PDV row exists for it — but a left join keeps the substitution table intact
    # if PDV is ever incomplete, rather than silently dropping detections.
    if pdv_ions is not None:
        second_psms = second_psms.join(
            pdv_ions.select(["spectrum_title", "dependent", "ions", "ion_mz", "ion_int"]),
            on=["spectrum_title", "dependent"],
            how="left",
        )

    # 9. Join first and second pass
    join_cols = ["base", "Charge"]
    # Ensure both have needed columns
    for c in join_cols:
        if c not in second_psms.columns:
            pass

    # `SpectralSim` and `RTScore` are FragPipe columns, carried verbatim out of
    # the second-pass psm.tsv (positions 18-19, right after `Delta Mass`) exactly
    # as the reference `analyze_outputs.py` does — it never computes them itself.
    #
    # FragPipe only writes them when MSBooster runs. Their absence therefore means
    # the second pass ran with MSBooster off, and the run is NOT reference-faithful.
    # This used to be papered over with null placeholders, which kept the schema
    # looking correct while every value was null for an entire session (D-069).
    # Fail loudly instead — a silent default over missing data is what hid the bug.
    missing_scores = [c for c in ("SpectralSim", "RTScore") if c not in second_psms.columns]
    if missing_scores:
        raise ValueError(
            f"Second-pass psm.tsv is missing {missing_scores}. FragPipe emits these "
            f"only when MSBooster runs; check that Step 3c did not disable it "
            f"(msbooster.run-msbooster / predict-rt / predict-spectra must be true). "
            f"Source: {second_psm_path}",
        )

    first_sub = first_psms.select([
        "Spectrum", "base", "Prev AA", "Next AA", "Protein",
        "first Intensity", "Retention", "Charge", "Protein Start",
        "Protein End", "Mapped Proteins", "Hyperscore",
        "Extended Peptide", "Number of Missed Cleavages", "Is Unique",
    ])

    joined = second_psms.join(first_sub, on=join_cols, suffix="_right")
    joined = _drop_decoy_rows(joined)

    # Reorder to match the reference schema. `SpectralSim`/`RTScore` sit straight
    # after `Delta Mass`; the PDV annotation trio sits straight after
    # `Traced Scans` (the last psm.tsv column), as in Slava's GAPDH subs.ipc.
    def _move_after(frame: pl.DataFrame, anchor: str, group: list[str]) -> pl.DataFrame:
        cols = list(frame.columns)
        if anchor not in cols or not all(c in cols for c in group):
            return frame
        cols = [c for c in cols if c not in group]
        idx = cols.index(anchor)
        return frame.select(cols[: idx + 1] + group + cols[idx + 1 :])

    joined = _move_after(joined, "Delta Mass", ["SpectralSim", "RTScore"])
    joined = _move_after(joined, "Traced Scans", ["ions", "ion_mz", "ion_int"])

    # 10. Extract substitution position from Protein field
    pos_pattern = r"_(?:\D*)(\d+)"
    joined = joined.with_columns(
        pl.col("Protein").str.extract(pos_pattern, 1)
        .cast(pl.Int64).alias("mistranslatedPos"),
    ).filter(pl.col("mistranslatedPos") > 0)

    # 11. Extract origin, destination, protein position.
    #
    # ORIGIN is read from `base`, NOT from the candidate header. The header carries
    # the collapsed class letter `I` for the whole isobaric pair (Step 3b), so taking
    # origin from it would mislabel every LEUCINE origin as `I`. But the origin is
    # known: it is the reference residue at the substituted position, and the genome
    # codon spells out I vs L. `base[mistranslatedPos]` is authoritative — there is
    # no such thing as an ambiguous `I/L` origin (D-065).
    #
    # DESTINATION stays the header's class letter `I` here; it is the misincorporated
    # residue, seen only by mass, so it is genuinely ambiguous. Step 11 relabels it
    # `I/L` as its last act — the `/` must not enter the mass lookup before then.
    sub_pattern = r"_(\w)(\d+)(\w)"
    joined = joined.with_columns([
        pl.col("base").str.slice(pl.col("mistranslatedPos"), 1).alias("origin"),
        pl.col("Protein").str.extract(sub_pattern, 3).alias("destination"),
        (
            pl.col("Protein Start_right") + pl.col("mistranslatedPos") - 1
        ).alias("misProt"),
    ])

    # 12. Abundance ratio
    ratio = (
        np.log10(
            joined["second Intensity"].to_numpy()
            / joined["first Intensity"].to_numpy(),
        )
    )
    joined = joined.with_columns(pl.Series("dpbp", ratio))

    output_ipc.parent.mkdir(parents=True, exist_ok=True)
    joined.write_ipc(output_ipc)
    return joined
