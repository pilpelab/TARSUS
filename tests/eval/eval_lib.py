"""Pure helpers for the step-07/11 regression eval.

Three responsibilities, all deterministic and tool-free so they run in
milliseconds under pytest:

- :func:`canonicalize` - collapse the two non-deterministic axes (row order,
  float representation) so a fresh ``subs.ipc`` can be compared to a committed
  golden by value.
- the ``check_*`` invariants - named guards that say *what* broke when they fail,
  each pinned to a real regression this project has hit (D-069, D-070, ``7502692``).
- :func:`slava_compare` - measure our output against Slava's like-for-like
  reference ``subs.ipc`` on the spectra they share: substitution identity and
  ``dpbp`` correlation, the same check the manual QC ran by hand.

None of these read a tool or the network; they operate on
:class:`polars.DataFrame` values only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

# Standard committed filenames inside each fixture's inputs/ directory. The
# builder writes these names; the test reads them - so the two never drift.
FIXTURE_INPUT_FILES: dict[str, str] = {
    "first_psm": "first_psm.tsv",
    "second_psm": "second_psm.tsv",
    "ptmall": "ptmall.txt",
    "psmrankall": "psmrankall.txt",
    "pdv": "pdv_export.txt",
    "psmrankall_base": "psmrankall_base.txt",
    "mgf": "spectra.mgf",
}

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES: list[str] = ["gapdh", "evcoli"]


def fixture_inputs(name: str) -> dict[str, Path]:
    """Absolute paths to a fixture's committed input files, keyed by role."""
    d = FIXTURES_DIR / name / "inputs"
    return {role: d / fn for role, fn in FIXTURE_INPUT_FILES.items()}


# Columns the committed Slava-reference projection must carry for slava_compare.
REFERENCE_COLUMNS: list[str] = [
    "Spectrum", "origin", "destination", "misProt", "Charge", "dpbp",
]


def fixture_reference(name: str) -> Path:
    """Path to the committed projection of Slava's reference subs.ipc.

    Only the columns :func:`slava_compare` needs, for the fixture's spectra - so
    the eval compares against Slava without reaching the (cluster-only) source.
    """
    return FIXTURES_DIR / name / "reference" / "subs_ref.ipc"


def fixture_golden(name: str) -> dict[str, Path]:
    """Absolute paths to a fixture's committed golden outputs, keyed by role."""
    d = FIXTURES_DIR / name / "golden"
    return {
        "subs": d / "subs.ipc",
        "subs_localized": d / "subs_localized.ipc",
        "subs_localized_csv": d / "subs_localized.csv",
    }

# The documented ``subs.ipc`` schema (docs/SUBS-SCHEMA.md): the 73 columns Step 7
# emits. A fixture may be a *superset* of this (gapdh's first-pass psm.tsv carries
# its own ions/ion_mz/ion_int, so the join adds `_right` copies) - the schema
# invariant therefore checks presence, not exact equality. The snapshot gate is
# what pins the exact per-fixture column set.
EXPECTED_SUBS_COLUMNS: list[str] = [
    "Spectrum", "Spectrum File", "dependent", "Modified Peptide",
    "Extended Peptide", "Prev AA", "Next AA", "Peptide Length", "Charge",
    "Retention", "Observed Mass", "Calibrated Observed Mass", "Observed M/Z",
    "Calibrated Observed M/Z", "Calculated Peptide Mass", "Calculated M/Z",
    "Delta Mass", "SpectralSim", "RTScore", "Expectation", "Hyperscore",
    "Nextscore", "Probability", "Qvalue", "Number of Enzymatic Termini",
    "Number of Missed Cleavages", "Protein Start", "Protein End",
    "second Intensity", "Assigned Modifications", "Observed Modifications",
    "Purity", "Is Decoy", "Is Contaminant", "Is Unique", "Protein",
    "Protein ID", "Entry Name", "Gene", "Protein Description", "Mapped Genes",
    "Mapped Proteins", "Parent Scan Number", "Apex Retention Time",
    "Apex Scan Number", "Retention Time Start", "Retention Time End",
    "Retention Time FWHM", "Traced Scans", "ions", "ion_mz", "ion_int", "base",
    "sample", "spectrum_title", "Spectrum_right", "Prev AA_right",
    "Next AA_right", "Protein_right", "first Intensity", "Retention_right",
    "Protein Start_right", "Protein End_right", "Mapped Proteins_right",
    "Hyperscore_right", "Extended Peptide_right",
    "Number of Missed Cleavages_right", "Is Unique_right", "mistranslatedPos",
    "origin", "destination", "misProt", "dpbp",
]

# Preferred sort keys, most-significant first. Only those present are used; any
# ties are then broken by every remaining column, so the order is a total order
# regardless of how the rows arrived.
_SORT_KEYS: list[str] = [
    "spectrum_title", "Spectrum", "dependent", "Charge", "misProt",
    "mistranslatedPos", "origin", "destination", "Protein", "base", "dpbp",
]

_FLOAT_DP = 6


def canonicalize(df: pl.DataFrame, float_dp: int = _FLOAT_DP) -> pl.DataFrame:
    """Return a deterministic form of *df* for snapshot equality.

    Rounds every float column to *float_dp* decimal places, then sorts by a
    total order over the columns. Row order and float representation are the two
    axes on which two runs of the same code over the same input can differ in
    their raw IPC bytes (spec risk 2); removing both lets us assert equality by
    value. Rounding happens *before* the sort so the sort keys are themselves
    stable.
    """
    float_cols = [c for c, t in zip(df.columns, df.dtypes)
                  if t in (pl.Float32, pl.Float64)]
    out = df
    if float_cols:
        out = out.with_columns([pl.col(c).round(float_dp) for c in float_cols])

    # Total order: preferred keys first, then every other column as a tiebreaker.
    lead = [c for c in _SORT_KEYS if c in out.columns]
    rest = [c for c in out.columns if c not in lead]
    sort_cols = lead + rest
    return out.sort(sort_cols, maintain_order=True)


def assert_snapshot_equal(fresh: pl.DataFrame, golden: pl.DataFrame) -> None:
    """Assert a fresh output matches a committed golden, after canonicalization.

    Raises ``AssertionError`` with polars' column/row diff when they differ, so a
    real behaviour change is legible rather than an opaque byte mismatch.
    """
    from polars.testing import assert_frame_equal

    if set(fresh.columns) != set(golden.columns):
        only_fresh = sorted(set(fresh.columns) - set(golden.columns))
        only_golden = sorted(set(golden.columns) - set(fresh.columns))
        raise AssertionError(
            "snapshot: column set changed. "
            f"fresh-only={only_fresh} golden-only={only_golden}"
        )
    a = canonicalize(fresh).select(sorted(fresh.columns))
    b = canonicalize(golden).select(sorted(golden.columns))
    assert_frame_equal(a, b, check_exact=False, abs_tol=1e-6, rel_tol=0.0,
                       check_dtypes=False)


# --------------------------------------------------------------------------- #
# Invariant guards - each raises AssertionError naming the regression it pins.
# --------------------------------------------------------------------------- #

def check_schema(df: pl.DataFrame) -> None:
    """Every documented ``subs.ipc`` column is present (superset allowed)."""
    missing = [c for c in EXPECTED_SUBS_COLUMNS if c not in df.columns]
    assert not missing, (
        f"schema: subs.ipc is missing documented columns {missing} "
        f"(see docs/SUBS-SCHEMA.md)"
    )


def check_no_decoys(df: pl.DataFrame) -> None:
    """No row is anchored on a ``rev_`` reverse-decoy protein (guards 7502692)."""
    cols = [c for c in ("Protein", "Protein_right") if c in df.columns]
    if not cols:
        return
    n = df.filter(
        pl.any_horizontal(
            [pl.col(c).cast(pl.Utf8).str.starts_with("rev_") for c in cols]
        )
    ).height
    assert n == 0, (
        f"rev_ decoy leak: {n} row(s) anchored on a rev_ protein reached "
        f"subs.ipc. The step07 decoy drop (commit 7502692) must remove these."
    )


def check_scores_nonnull(df: pl.DataFrame) -> None:
    """``SpectralSim``/``RTScore`` present and fully populated (guards D-069)."""
    for c in ("SpectralSim", "RTScore"):
        assert c in df.columns, (
            f"{c} column absent - MSBooster was off in the second pass (D-069)"
        )
        n_null = df[c].null_count()
        assert n_null == 0, (
            f"{c} has {n_null} null value(s) - MSBooster was off in the "
            f"second pass, so FragPipe never wrote this column (D-069)"
        )


def check_dpbp_finite(df: pl.DataFrame) -> None:
    """Every ``dpbp`` substitution rate is finite (no null/NaN/inf)."""
    assert "dpbp" in df.columns, "dpbp column absent"
    bad = df.filter(
        pl.col("dpbp").is_null()
        | pl.col("dpbp").is_nan()
        | pl.col("dpbp").is_infinite()
    ).height
    assert bad == 0, f"dpbp has {bad} non-finite value(s) (null/NaN/inf)"


def run_all_invariants(df: pl.DataFrame) -> None:
    """Run every step-07 invariant guard; the first failure raises."""
    check_schema(df)
    check_no_decoys(df)
    check_scores_nonnull(df)
    check_dpbp_finite(df)


# --------------------------------------------------------------------------- #
# Comparison against Slava's like-for-like reference subs.ipc.
# --------------------------------------------------------------------------- #

def _il_norm(expr: pl.Expr) -> pl.Expr:
    """I/L-normalize a residue label: Leu and the collapsed class both -> ``I``."""
    return expr.cast(pl.Utf8).str.replace_all("L", "I", literal=True)


def _spectrum_key(df: pl.DataFrame) -> pl.DataFrame:
    """Attach a ``_key`` column = the ``file:scan:charge`` spectrum title.

    Our output carries it as ``spectrum_title``; Slava's reference has no such
    column but its ``Spectrum`` column is already the colon form, so it *is* the
    key.
    """
    if "spectrum_title" in df.columns:
        return df.with_columns(pl.col("spectrum_title").alias("_key"))
    if "Spectrum" in df.columns:
        return df.with_columns(pl.col("Spectrum").alias("_key"))
    raise ValueError("frame has neither 'spectrum_title' nor 'Spectrum'")


@dataclass
class SlavaComparison:
    """Result of comparing our output to Slava's reference on shared spectra."""

    n_shared_spectra: int
    n_matching_spectra: int
    identity_fraction: float
    dpbp_pearson_r: float
    n_dpbp_pairs: int

    def assert_ok(self, min_identity: float = 1.0, min_r: float = 0.99) -> None:
        """Raise if identity or dpbp correlation falls below the eval bar."""
        assert self.n_shared_spectra > 0, (
            "slava_compare: no shared spectra between our output and the "
            "reference - the slice broke lineage (D-047), it is not a code bug"
        )
        assert self.identity_fraction >= min_identity, (
            f"slava_compare: substitution identity {self.identity_fraction:.4f} "
            f"< {min_identity} on {self.n_shared_spectra} shared spectra "
            f"({self.n_matching_spectra} matched)"
        )
        assert self.dpbp_pearson_r >= min_r, (
            f"slava_compare: dpbp Pearson r {self.dpbp_pearson_r:.4f} < {min_r} "
            f"over {self.n_dpbp_pairs} paired rows"
        )


def _substitution_signature(df: pl.DataFrame) -> dict[str, set[tuple[str, str, int]]]:
    """Map each spectrum -> its set of (origin, dest, misProt) substitution calls.

    Residue labels are I/L-normalized so an ``I`` vs ``L`` labelling difference
    never counts as a substitution disagreement.
    """
    keyed = _spectrum_key(df).with_columns(
        _il_norm(pl.col("origin")).alias("_o"),
        _il_norm(pl.col("destination")).alias("_d"),
    )
    sig: dict[str, set[tuple[str, str, int]]] = {}
    for r in keyed.select(["_key", "_o", "_d", "misProt"]).iter_rows():
        sig.setdefault(r[0], set()).add((r[1], r[2], r[3]))
    return sig


def slava_compare(ours: pl.DataFrame, ref: pl.DataFrame) -> SlavaComparison:
    """Compare our subs.ipc to Slava's reference on the spectra they share.

    - **Substitution identity:** for every shared spectrum, the *set* of
      ``(origin, destination, misProt)`` calls must match exactly (I/L-normalized).
      A carbamidomethyl-Cys or oxidised-Met row silently dropped by re-anchoring
      the modification regex (D-070) shows up here as a mismatched spectrum.
    - **dpbp correlation:** Pearson r of ``dpbp`` over rows paired on
      ``(spectrum_title, misProt, destination, Charge)``. Same inputs -> same
      ratios, so a divergence means the abundance join changed.
    """
    ours_sig = _substitution_signature(ours)
    ref_sig = _substitution_signature(ref)
    shared = sorted(set(ours_sig) & set(ref_sig))
    n_match = sum(1 for k in shared if ours_sig[k] == ref_sig[k])
    identity = n_match / len(shared) if shared else 0.0

    # Pair rows for dpbp correlation.
    ok = _spectrum_key(ours).with_columns(
        _il_norm(pl.col("destination")).alias("_d")
    ).select(["_key", "misProt", "_d", "Charge", "dpbp"])
    rk = _spectrum_key(ref).with_columns(
        _il_norm(pl.col("destination")).alias("_d")
    ).select(["_key", "misProt", "_d", "Charge", "dpbp"])
    paired = ok.join(
        rk, on=["_key", "misProt", "_d", "Charge"], how="inner", suffix="_ref"
    ).drop_nulls(["dpbp", "dpbp_ref"])

    if paired.height >= 2:
        r = paired.select(pl.corr("dpbp", "dpbp_ref")).item()
        r = float(r) if r is not None else 1.0
    else:
        # 0 or 1 paired rows: correlation is undefined. Fall back to exact
        # agreement so a tiny slice cannot silently pass on noise.
        r = 1.0 if paired.height == 0 or (
            abs(paired["dpbp"][0] - paired["dpbp_ref"][0]) < 1e-6
        ) else 0.0

    return SlavaComparison(
        n_shared_spectra=len(shared),
        n_matching_spectra=n_match,
        identity_fraction=identity,
        dpbp_pearson_r=r,
        n_dpbp_pairs=paired.height,
    )
