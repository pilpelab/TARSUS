"""Step 12: Generate publication-quality SAAV visualizations.

Reads subs_localized.ipc from Step 11 and produces standard plots:
  1. Substitution matrix heatmap (origin x destination counts)
  2. Substitution counts by group (WT vs mutant bar chart)
  3. dpbp intensity ratio distributions by group
  4. Amino acid origin frequencies

Auto-detects sample groups from spectrum_title prefixes.
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib
import numpy as np
import polars as pl
import seaborn as sns
from matplotlib import pyplot as plt

matplotlib.use("Agg")  # headless — no X11 needed

# Canonical amino acid order for heatmaps (standard proteomics ordering).
_AA_ORDER = list("GALMFWKQESPVICYHRNTD-")


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
# Main step entry point
# ---------------------------------------------------------------------------


def step12_visualize(
    localized_ipc: Path,
    output_dir: Path,
    *,
    dpi: int = 150,
) -> Path:
    """Generate SAAV visualizations from localized results.

    Args:
        localized_ipc: Path to subs_localized.ipc from Step 11.
        output_dir: Directory where 12_visualize/ will be created.
        dpi: Output resolution.

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

    return viz_dir
