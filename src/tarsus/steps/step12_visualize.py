"""Step 12: Generate publication-quality SAAV visualizations.

Reads subs_localized.ipc from Step 11 and produces standard plots:
  1. Substitution matrix heatmap (origin x destination counts)
  2. Substitution counts by group (WT vs mutant bar chart)
  3. dpbp intensity ratio distributions by group
  4. Amino acid origin frequencies
  5. **The 61x19 codon heatmap** — the lab's canonical figure, ported from
     ``SubsToSixtyTwentyWithMask.py``. Needs a CDS FASTA (``--cds``); skipped with a
     loud warning when absent, never silently.

Auto-detects sample groups from spectrum_title prefixes.
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle

from ..codons import (
    ALL_AA,
    ALL_CODONS,
    GENCODE,
    NECE_MASK_CSV,
    SIXTY_TWENTY_MASK_CSV,
    codon_counts,
    load_cds,
    rna_to_dna,
)

matplotlib.use("Agg")  # headless — no X11 needed

# Canonical amino acid order for heatmaps (standard proteomics ordering).
#
# Ile and Leu are isobaric and the pipeline collapses them onto one class, which
# Step 11 labels `I/L` on its way out (D-064). Neither bare `I` nor bare `L` can
# reach a plot, so the merged class takes Leu's slot and Ile's is dropped.
_AA_ORDER = ["G", "A", "I/L", "M", "F", "W", "K", "Q", "E", "S",
             "P", "V", "C", "Y", "H", "R", "N", "T", "D", "-"]


def _detect_groups(df: pl.DataFrame) -> dict[str, str]:
    """Map each spectrum_title to a group label inferred from the filename.

    Scans the spectrum_title column for known group tokens.
    Returns dict of spectrum_title -> group.
    """
    titles = df["spectrum_title"].unique().to_list()
    mapping: dict[str, str] = {}

    for title in titles:
        # Look for L73/WT markers in the filename portion (before first colon).
        fname = title.split(":")[0] if ":" in title else title
        if "L73" in fname:
            mapping[title] = "L73 (mutant)"
        elif "WT" in fname:
            mapping[title] = "WT"
        else:
            # Fallback: use the first underscore-delimited token after EX1_OR_
            m = re.match(r"EX1_OR_\d+_([A-Za-z0-9]+)", fname)
            mapping[title] = m.group(1) if m else fname

    return mapping


def _ensure_aa_order(values: list[str]) -> list[str]:
    """Return values sorted by _AA_ORDER, with unknowns appended."""
    idx = {aa: i for i, aa in enumerate(_AA_ORDER)}
    return sorted(values, key=lambda x: idx.get(x, len(_AA_ORDER)))


# ---------------------------------------------------------------------------
# Plot functions
# ---------------------------------------------------------------------------


def _plot_substitution_heatmap(df: pl.DataFrame, out: Path) -> None:
    """Origin x destination count heatmap."""
    mat = (
        df.group_by(["origin", "destination"])
        .len()
        .pivot(index="origin", on="destination", values="len")
        .fill_null(0)
    )
    # Build a full square matrix on _AA_ORDER.
    origins = _ensure_aa_order(mat["origin"].to_list())
    dests = _ensure_aa_order(
        [c for c in mat.columns if c not in ("origin",)]
    )
    all_aas = _ensure_aa_order(list(set(origins + dests)))

    data = np.zeros((len(all_aas), len(all_aas)))
    row_idx = {aa: i for i, aa in enumerate(all_aas)}
    for row in mat.iter_rows(named=True):
        o = row["origin"]
        if o not in row_idx:
            continue
        for d in dests:
            if d not in row_idx:
                continue
            data[row_idx[o]][row_idx[d]] = row.get(d, 0) or 0

    fig, ax = plt.subplots(figsize=(10, 8))
    mask = np.eye(len(all_aas), dtype=bool)
    sns.heatmap(
        data,
        xticklabels=all_aas,
        yticklabels=all_aas,
        mask=mask,
        square=True,
        cmap="YlOrRd",
        linewidths=0.5,
        linecolor="white",
        annot=True,
        fmt=".0f",
        annot_kws={"size": 7},
        ax=ax,
    )
    ax.set_title("Localized SAAV Substitutions")
    ax.set_xlabel("Destination amino acid")
    ax.set_ylabel("Origin amino acid")
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_grouped_bars(df: pl.DataFrame, out: Path) -> None:
    """Bar chart of substitution counts split by group."""
    groups = df["_group"].unique().to_list()
    if len(groups) < 2:
        # Single group — simple top-N bar chart.
        counts = (
            df.with_columns(
                (pl.col("origin") + "\u2192" + pl.col("destination")).alias("sub")
            )
            .group_by("sub")
            .len()
            .sort("len", descending=True)
            .head(20)
        )
        fig, ax = plt.subplots(figsize=(10, 5))
        sns.barplot(data=counts.to_pandas(), x="sub", y="len", color="steelblue", ax=ax)
        ax.set_title("Top Substitutions (single group)")
        ax.set_xlabel("Substitution")
        ax.set_ylabel("Count")
        ax.tick_params(axis="x", rotation=45)
    else:
        df2 = df.with_columns(
            (pl.col("origin") + "\u2192" + pl.col("destination")).alias("sub")
        )
        counts = (
            df2.group_by(["sub", "_group"])
            .len()
            .sort("len", descending=True)
        )
        top_subs = (
            counts.group_by("sub").agg(pl.col("len").sum())
            .sort("len", descending=True)
            .head(20)["sub"]
            .to_list()
        )
        plot_df = counts.filter(pl.col("sub").is_in(top_subs)).to_pandas()
        fig, ax = plt.subplots(figsize=(12, 5))
        sns.barplot(data=plot_df, x="sub", y="len", hue="_group", ax=ax)
        ax.set_title("Top Substitutions by Group")
        ax.set_xlabel("Substitution")
        ax.set_ylabel("Count")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(title="")
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_dpbp_distribution(df: pl.DataFrame, out: Path) -> None:
    """dpbp (log10 variant/ref intensity ratio) distributions by group."""
    groups = df["_group"].unique().to_list()
    fig, ax = plt.subplots(figsize=(8, 4))

    if len(groups) < 2:
        sns.histplot(
            df["dpbp"].to_pandas(), kde=True, color="steelblue", ax=ax
        )
        ax.set_title("dpbp Distribution (single group)")
    else:
        for grp in groups:
            sns.kdeplot(
                data=df.filter(pl.col("_group") == grp)["dpbp"].to_pandas(),
                label=grp,
                fill=True,
                alpha=0.3,
                ax=ax,
            )
        ax.set_title("dpbp Distribution by Group")
        ax.legend(title="")

    ax.set_xlabel("dpbp (log10 variant / reference intensity)")
    ax.set_ylabel("Density")
    ax.axvline(0, color="gray", linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_origin_frequencies(df: pl.DataFrame, out: Path) -> None:
    """Origin amino acid frequency bar chart."""
    groups = df["_group"].unique().to_list()
    if len(groups) < 2:
        counts = (
            df.group_by("origin").len()
            .sort("origin")
            .to_pandas()
        )
        fig, ax = plt.subplots(figsize=(8, 4))
        sns.barplot(data=counts, x="origin", y="len", color="steelblue", ax=ax)
        ax.set_title("Origin Amino Acid Frequencies")
    else:
        counts = (
            df.group_by(["origin", "_group"])
            .len()
            .to_pandas()
        )
        fig, ax = plt.subplots(figsize=(10, 4))
        sns.barplot(data=counts, x="origin", y="len", hue="_group", ax=ax)
        ax.set_title("Origin Amino Acid Frequencies by Group")
        ax.legend(title="")
    ax.set_xlabel("Origin amino acid")
    ax.set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# The 61x19 codon heatmap — the lab's canonical figure
# ---------------------------------------------------------------------------


def build_sixty_twenty(
    df: pl.DataFrame, cds_fasta: Path,
) -> tuple[pd.DataFrame, int]:
    """Build the 61 codon x 19 amino-acid substitution matrix.

    Mistranslation happens in **codon** space, not amino-acid space: an engineered
    tRNA reads one specific codon. `AlaGGC` inserts Ala at **GGC** — and Gly has four
    codons, so an amino-acid-level ``G->A`` count smears the signal across three codons
    the tRNA never touches. This is the resolution the experiment actually happens at.

    Returns:
        ``(matrix, n_unresolved)``. The caller **must** surface *n_unresolved* — a
        substitution whose codon cannot be resolved is dropped from the figure, and a
        silently-dropped row is the D-057 failure mode.
    """
    rows = [
        (str(r["base"]), int(r["mistranslated_pos"]), str(r["destination"]))
        for r in df.iter_rows(named=True)
    ]
    cds = load_cds(cds_fasta)
    if not cds:
        raise ValueError(f"No usable CDS records in {cds_fasta}")

    counts, unresolved = codon_counts(rows, cds)

    mat = pd.DataFrame(0.0, index=ALL_CODONS, columns=ALL_AA)
    for (codon, dest), n in counts.items():
        if codon in mat.index and dest in mat.columns:
            mat.loc[codon, dest] = float(n)
    return mat, unresolved


def _multiindex_codon_aa(mat: pd.DataFrame) -> pd.DataFrame:
    """Index rows by (codon, its amino acid), sorted by amino acid — the lab's layout."""
    idx = pd.MultiIndex.from_tuples(
        [(c, GENCODE[c]) for c in mat.index], names=["codons", "amino acid"],
    )
    return mat.set_index(idx).sort_index(level=1)


def _load_masks(mat_index: pd.Index, columns: pd.Index) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    """The grey-out mask and the near-cognate-error cells.

    The two files disagree on alphabet — `SixtyTwentyMask` is indexed by RNA codons
    (``UUU``), `NeCEMask` by DNA (``TTT``). Reconciled here rather than assumed.
    """
    grey = pd.read_csv(SIXTY_TWENTY_MASK_CSV, index_col=0)
    grey.index = pd.Index([rna_to_dna(c) for c in grey.index])
    grey = grey.reindex(index=[c for c, _ in mat_index], columns=columns).fillna(False)
    grey = _multiindex_codon_aa(grey)

    nece = pd.read_csv(NECE_MASK_CSV, index_col=0)
    nece = nece.reindex(index=[c for c, _ in mat_index], columns=columns).fillna(False)
    cells = [
        (j, i)
        for i in range(nece.shape[0])
        for j in range(nece.shape[1])
        if bool(nece.iloc[i, j])
    ]
    return grey, cells


def _plot_sixty_twenty(
    mat: pd.DataFrame, out: Path, title: str, dpi: int,
) -> None:
    """Draw one 61x19 heatmap: codons down, destination amino acids across."""
    grey, nece = _load_masks(mat.index, mat.columns)

    fig, ax = plt.subplots(figsize=(8, 16))
    sns.heatmap(
        mat, square=True, cmap="Reds", ax=ax,
        cbar_kws={"shrink": 0.3}, linewidths=0.5, mask=grey.values.astype(bool),
    )
    ax.set_title(title, pad=18)
    ax.set_facecolor("gray")
    ax.set_ylabel("")

    # Near-cognate-error cells — reachable by a single nucleotide change.
    for j, i in nece:
        ax.add_patch(Rectangle((j + 0.45, i + 0.45), 0.25, 0.25,
                               facecolor="black", edgecolor="none", lw=0))

    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main step entry point
# ---------------------------------------------------------------------------


def step12_visualize(
    localized_ipc: Path,
    output_dir: Path,
    *,
    dpi: int = 150,
    cds_fasta: Path | None = None,
) -> Path:
    """Generate SAAV visualizations from localized results.

    Args:
        localized_ipc: Path to subs_localized.ipc from Step 11.
        output_dir: Directory where 12_visualize/ will be created.
        dpi: Output resolution.
        cds_fasta: CDS (nucleotide) FASTA for the organism. Required for the 61x19
            codon heatmap — without it that figure is **skipped with a loud warning**,
            never silently.

    Returns:
        Path to the visualize output directory.
    """
    if not localized_ipc.is_file():
        raise FileNotFoundError(f"subs_localized.ipc not found: {localized_ipc}")

    df = pl.read_ipc(localized_ipc)
    if df.is_empty():
        raise ValueError("No localized SAAVs to visualize — subs_localized.ipc is empty")

    viz_dir = output_dir / "12_visualize"
    viz_dir.mkdir(parents=True, exist_ok=True)

    # Infer groups from spectrum titles.
    group_map = _detect_groups(df)
    df = df.with_columns(
        pl.col("spectrum_title").replace(group_map).alias("_group")
    )

    # Set seaborn style.
    sns.set_context("talk", font_scale=0.9)
    sns.set_style("whitegrid")

    # Generate plots.
    _plot_substitution_heatmap(df, viz_dir / "substitution_heatmap.png")
    _plot_grouped_bars(df, viz_dir / "top_substitutions.png")
    _plot_dpbp_distribution(df, viz_dir / "dpbp_distribution.png")
    _plot_origin_frequencies(df, viz_dir / "origin_frequencies.png")

    # The 61x19 codon heatmap. Needs a CDS FASTA; say so out loud when absent.
    if cds_fasta is None or not Path(cds_fasta).is_file():
        print(
            f"[step12] SKIPPING the 61x19 codon heatmap: no CDS FASTA "
            f"({cds_fasta or 'not supplied'}). Mistranslation happens in codon space "
            f"— an engineered tRNA reads ONE codon — so without this the "
            f"amino-acid-level counts smear the signal across synonymous codons. "
            f"Pass --cds <cds.fasta> to produce it."
        )
        return viz_dir

    mat, unresolved = build_sixty_twenty(df, Path(cds_fasta))
    if unresolved:
        print(
            f"[step12] {unresolved} of {df.height} substitutions had no unambiguous "
            f"codon (peptide absent from the CDS, or mapping to proteins that "
            f"disagree) and are EXCLUDED from the 61x19 heatmap."
        )

    sns.set_context("poster", font_scale=0.7)
    mat_mi = _multiindex_codon_aa(mat)
    mat_mi.to_csv(viz_dir / "sixty_twenty.csv")
    _plot_sixty_twenty(mat_mi, viz_dir / "sixty_twenty.png",
                       "Substitutions per codon", dpi)

    log_mi = pd.DataFrame(
        np.log2(mat_mi.values + 1), index=mat_mi.index, columns=mat_mi.columns,
    )
    _plot_sixty_twenty(log_mi, viz_dir / "sixty_twenty_log.png",
                       "Substitutions per codon (log2 + 1)", dpi)
    sns.set_context("talk", font_scale=0.9)

    total = int(mat.values.sum())
    print(f"[step12] 61x19 codon heatmap: {total:,} substitutions placed on codons")
    return viz_dir
