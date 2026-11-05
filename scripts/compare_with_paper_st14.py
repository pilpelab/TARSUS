"""Compare TARSUS outputs for the purified QC proteins against the paper's ST14.

Supplementary Table 14 of Tretyachenko et al. (Nature 2026) is the published
final substitution list for the in-house purified proteins (GAPDH, hemoglobin,
PARK7, PRDX6). This script reports, per protein, how many of ST14's unique
substituted peptides appear in each given ``subs.ipc`` (Step 7 candidates) or
``subs_localized.ipc`` (Step 11 final).

Unit: unique substituted peptide sequence (the paper's "unique substitution"),
with Leu normalised to Ile on both sides (MS cannot tell them apart). On a Step 7
table the recall is the ceiling for what Step 11 can recover; on a Step 11 table
it is the like-for-like comparison.

Usage::

    uv run python scripts/fetch_paper_supplements.py          # once, for ST14
    uv run python scripts/compare_with_paper_st14.py \\
        --table GAPDH=Barc:path/to/subs.ipc --table GAPDH=Slava:path/to/subs.ipc ...
    uv run python scripts/compare_with_paper_st14.py --qc-step7   # recovered QC panel

Interpretation notes: ``.context/paper-supplementary-tables.md`` (ST14 row).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

ST14 = Path("data/paper/tsv/Supplementary_Table14__purified_proteins.tsv")
ST14_SAMPLES = ("GAPDH", "Hb", "PARK7", "PRDX6")
SLAVA_BASE = Path("/home/labs/pilpel/slavat/tehilapaper/revisions/hoMS")
BARC_QC = Path(".scratch/qc-recovered/docs/qc-history/subs")
#: The recovered D-072 QC panel: Step 7 subs.ipc for Barc and Slava.
QC_STEP7: dict[str, dict[str, Path]] = {
    "GAPDH": {"Barc": BARC_QC / "homs_24814.ipc",
              "Slava": SLAVA_BASE / "GAPDH/2d/fragpipe_fullpipeline/subs.ipc"},
    "Hb": {"Barc": BARC_QC / "hemoglobin.ipc",
           "Slava": SLAVA_BASE / "hemoglobin/2d/fragpipe/subs.ipc"},
    "PARK7": {"Barc": BARC_QC / "park7.ipc", "Slava": SLAVA_BASE / "PARK7/2d/fragpipe/subs.ipc"},
    "PRDX6": {"Barc": BARC_QC / "prdx6.ipc", "Slava": SLAVA_BASE / "PRDX6/2d/fragpipe/subs.ipc"},
}


def _norm(seqs: pl.Series) -> set[str]:
    """Unique peptide sequences with Leu normalised to Ile."""
    return set(seqs.drop_nulls().str.replace_all("L", "I").to_list())


def load_st14(path: Path = ST14) -> dict[str, set[str]]:
    """Unique ST14 substituted peptides per purified-protein sample.

    Raises:
        FileNotFoundError: ST14 TSV missing (run ``fetch_paper_supplements.py``).
    """
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; run scripts/fetch_paper_supplements.py")
    st14 = pl.read_csv(path, separator="\t", infer_schema_length=None)
    return {s: _norm(st14.filter(pl.col("sample") == s)["alt_peptide"]) for s in ST14_SAMPLES}


def load_table(path: Path) -> set[str]:
    """Unique ``dependent`` (substituted peptide) sequences of a TARSUS IPC table.

    Raises:
        FileNotFoundError: the table does not exist.
        KeyError: the table has no ``dependent`` column.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    df = pl.read_ipc(path, memory_map=False)
    if "dependent" not in df.columns:
        raise KeyError(f"{path} has no 'dependent' column")
    return _norm(df["dependent"])


def compare(tables: dict[str, dict[str, Path]]) -> pl.DataFrame:
    """One row per (protein, source): ST14 recall and table size.

    Args:
        tables: ``{st14_sample: {source_label: ipc_path}}``.
    """
    st14 = load_st14()
    rows = []
    for sample, sources in tables.items():
        ref = st14[sample]
        for label, path in sources.items():
            got = load_table(path)
            hit = ref & got
            rows.append({
                "protein": sample, "source": label, "st14_unique": len(ref),
                "table_unique": len(got), "st14_found": len(hit),
                "recall_pct": round(100 * len(hit) / len(ref), 1) if ref else None,
            })
    return pl.DataFrame(rows)


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code.
    """
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--table", action="append", default=[],
                    help="SAMPLE=LABEL:PATH, SAMPLE in GAPDH/Hb/PARK7/PRDX6")
    ap.add_argument("--qc-step7", action="store_true",
                    help="compare the recovered D-072 QC panel (Step 7) for Barc and Slava")
    args = ap.parse_args()
    tables: dict[str, dict[str, Path]] = {}
    if args.qc_step7:
        tables = {k: dict(v) for k, v in QC_STEP7.items()}
    for spec in args.table:
        sample, _, rest = spec.partition("=")
        label, _, path = rest.partition(":")
        if sample not in ST14_SAMPLES or not label or not path:
            ap.error(f"bad --table {spec!r}; expected SAMPLE=LABEL:PATH")
        tables.setdefault(sample, {})[label] = Path(path)
    if not tables:
        ap.error("give --qc-step7 and/or --table")
    with pl.Config(tbl_rows=-1, tbl_hide_dataframe_shape=True):
        print(compare(tables))
    return 0


if __name__ == "__main__":
    sys.exit(main())
