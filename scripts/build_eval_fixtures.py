#!/usr/bin/env python
"""Build (and re-bless) the step-07/11 regression eval fixtures.

For each fixture this script:

1. Picks a lineage-coherent ~100-spectrum slice of the reference run, chosen
   from spectra that appear in Slava's like-for-like reference ``subs.ipc`` and
   deliberately covering the failure modes the eval must guard (Cys-/Met-origin
   substitutions for D-070, I/L destinations, several charges, and - for gapdh -
   a synthetic reverse-decoy row for the ``7502692`` guard).
2. Slices every step-07/11 input to exactly that spectrum set, by streaming text
   so the bytes stay faithful (no polars re-serialization of ragged tool output).
3. Runs the real ``analyze_outputs`` / ``localize`` on the slice to produce the
   golden outputs.
4. Asserts, at build time, that the slice is non-empty, passes every invariant,
   and still matches Slava's reference on the shared spectra. A silent empty
   result means the slice broke lineage (D-047), not that the code is wrong - so
   it fails loudly here rather than committing a hollow fixture.

Re-runnable: pass ``--fixture gapdh|evcoli|all``. Re-running (re)blesses the
goldens deterministically from the reference dirs.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import polars as pl  # noqa: E402

from tarsus.steps.step07_analyze_outputs import (  # noqa: E402
    _spectrum_to_title,
    analyze_outputs,
)
from tarsus.steps import step07_analyze_outputs as _s7  # noqa: E402
from tarsus.steps.step11_localize import localize  # noqa: E402
from tests.eval import eval_lib as L  # noqa: E402

TARGET_SPECTRA = 100


@dataclass
class RefSpec:
    """A reference run directory and where each step-07/11 input lives in it."""

    name: str
    base: Path
    inject_decoy: bool  # synthesize a rev_ row (only where the source has none)

    def path(self, *parts: str) -> Path:
        return self.base.joinpath(*parts)


REFS: dict[str, RefSpec] = {
    "gapdh": RefSpec(
        name="gapdh",
        base=Path("/home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/"
                  "GAPDH/2d/fragpipe_fullpipeline"),
        inject_decoy=True,
    ),
    "evcoli": RefSpec(
        name="evcoli",
        base=Path("/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis"),
        inject_decoy=False,
    ),
}


# --------------------------------------------------------------------------- #
# Spectrum selection - coverage-driven and deterministic.
# --------------------------------------------------------------------------- #

def _base_covered_spectra(ref: RefSpec) -> set[str]:
    """spectrum_titles that have a base entry in psmrankall_base (step-11 needs
    these to produce any localized row)."""
    import re
    suf = re.compile(r"_M(?:\d+(?:_\d+)*)C(?:\d+(?:_\d+)*)$")
    df = pl.read_csv(ref.path("psmrankall_base.txt"), separator="\t",
                     columns=["spectrum_title"], truncate_ragged_lines=True,
                     infer_schema_length=0)
    return {suf.sub("", t) for t in df["spectrum_title"].to_list()}


def select_spectra(ref: RefSpec, slava: pl.DataFrame) -> list[str]:
    """Choose ~``TARGET_SPECTRA`` reference spectra with required coverage.

    Deterministic: every pick is the first match in Spectrum-sorted order, and
    the fill prefers step-11-covered spectra so ``localize`` has candidates.
    """
    s = slava.sort("Spectrum")
    chosen: list[str] = []
    seen: set[str] = set()

    def add(spectrum: str) -> None:
        if spectrum and spectrum not in seen:
            seen.add(spectrum)
            chosen.append(spectrum)

    def first_where(expr: pl.Expr) -> str | None:
        hit = s.filter(expr).head(1)
        return hit["Spectrum"].item() if hit.height else None

    # Required coverage: Cys origin, Met origin (D-070), an I/L destination, and
    # every charge present in the reference (multi-charge coverage).
    for expr in (
        pl.col("origin") == "C",
        pl.col("origin") == "M",
        pl.col("destination") == "I",
    ):
        got = first_where(expr)
        if got:
            add(got)
    for ch in sorted(s["Charge"].unique().to_list()):
        got = first_where(pl.col("Charge") == ch)
        if got:
            add(got)

    # Fill to target: step-11-covered spectra first, then the rest, both in
    # Spectrum-sorted order.
    covered = _base_covered_spectra(ref)
    ordered = s["Spectrum"].unique(maintain_order=True).to_list()
    for pool in (
        [sp for sp in ordered if sp in covered],
        [sp for sp in ordered if sp not in covered],
    ):
        for sp in pool:
            if len(chosen) >= TARGET_SPECTRA:
                break
            add(sp)
        if len(chosen) >= TARGET_SPECTRA:
            break
    return chosen


# --------------------------------------------------------------------------- #
# Text-streaming slicers - keep tool output byte-faithful.
# --------------------------------------------------------------------------- #

def _header_fields(path: Path) -> list[str]:
    with open(path, errors="replace") as f:
        return f.readline().rstrip("\n").split("\t")


def slice_headerless(src: Path, dst: Path, field: int, keys: set[str]) -> int:
    n = 0
    with open(src, errors="replace") as fi, open(dst, "w") as fo:
        for line in fi:
            parts = line.rstrip("\n").split("\t")
            if len(parts) > field and parts[field] in keys:
                fo.write(line)
                n += 1
    return n


def slice_with_header(src: Path, dst: Path, field: int, keys: set[str],
                      transform: Callable[[str], str] | None = None) -> int:
    n = 0
    with open(src, errors="replace") as fi, open(dst, "w") as fo:
        fo.write(fi.readline())
        for line in fi:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= field:
                continue
            key = parts[field]
            if transform is not None:
                key = transform(key)
            if key in keys:
                fo.write(line)
                n += 1
    return n


def slice_second_psm(src: Path, dst: Path, keys: set[str]) -> tuple[int, set[str]]:
    """Slice second-pass psm.tsv by converted spectrum title; return
    (rows, bases). Bases drive the first-pass slice's (base, Charge) join set."""
    hdr = _header_fields(src)
    si, pi = hdr.index("Spectrum"), hdr.index("Protein")
    bases: set[str] = set()
    n = 0
    with open(src, errors="replace") as fi, open(dst, "w") as fo:
        fo.write(fi.readline())
        for line in fi:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= max(si, pi):
                continue
            if _spectrum_to_title(parts[si]) in keys:
                fo.write(line)
                n += 1
                bases.add(parts[pi].split("_")[0])
    return n, bases


def slice_first_psm(src: Path, dst: Path, bases: set[str]) -> int:
    """Keep only the max-``Intensity`` first-pass row(s) per (base, Charge).

    Step 7 filters first-pass PSMs to ``first Intensity == max over (base, Charge)``
    before joining, so keeping *only* those winners is result-identical to keeping
    every row for a base - and orders of magnitude smaller (a base peptide can be
    identified in hundreds of scans). Ties at the max are all kept, matching step 7.
    Two text passes keep the tool's bytes faithful.
    """
    hdr = _header_fields(src)
    pep, chg, inten = hdr.index("Peptide"), hdr.index("Charge"), hdr.index("Intensity")
    wide = max(pep, chg, inten)

    def parse_intensity(s: str) -> float:
        try:
            return float(s)
        except ValueError:
            return 0.0

    # Pass 1: max intensity per (base, Charge) over positive-intensity rows.
    best: dict[tuple[str, str], float] = {}
    with open(src, errors="replace") as fi:
        fi.readline()
        for line in fi:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= wide or parts[pep] not in bases:
                continue
            v = parse_intensity(parts[inten])
            if v <= 0:
                continue
            k = (parts[pep], parts[chg])
            if v > best.get(k, -1.0):
                best[k] = v

    # Pass 2: write header + every row tying its group's max.
    n = 0
    with open(src, errors="replace") as fi, open(dst, "w") as fo:
        fo.write(fi.readline())
        for line in fi:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= wide or parts[pep] not in bases:
                continue
            v = parse_intensity(parts[inten])
            if v > 0 and v == best.get((parts[pep], parts[chg])):
                fo.write(line)
                n += 1
    return n


def slice_mgf(src: Path, dst: Path, keys: set[str]) -> int:
    n = 0
    with open(src, errors="replace") as fi, open(dst, "w") as fo:
        block: list[str] = []
        title: str | None = None
        for line in fi:
            if line.startswith("BEGIN IONS"):
                block, title = [line], None
            elif line.startswith("TITLE="):
                title = line[6:].strip()
                block.append(line)
            elif line.startswith("END IONS"):
                block.append(line)
                if title in keys:
                    fo.writelines(block)
                    n += 1
                block, title = [], None
            else:
                block.append(line)
    return n


def inject_decoy_row(first_psm: Path, golden: pl.DataFrame) -> str:
    """Append a synthetic reverse-decoy first-pass row to *first_psm*.

    The row duplicates a real first-pass PSM that already joins into the golden,
    but with its Protein renamed ``rev_...`` and identical ``first Intensity`` (a
    tie, so it survives step 7's max-over-(base,Charge) filter). On join it
    produces a ``rev_``-anchored row that current code (commit ``7502692``) drops
    - so the golden is unchanged - yet reverting that drop resurrects it, which is
    exactly the regression this fixture must catch. Returns the rev_ protein id.
    """
    hdr = _header_fields(first_psm)
    spec_i, prot = hdr.index("Spectrum"), hdr.index("Protein")
    want = golden.select(["base", "Charge"]).head(1).to_dicts()[0]
    base, charge = str(want["base"]), int(want["Charge"])

    # The injected row must tie the per-(base, Charge) MAX first Intensity, or
    # step 7's max filter drops it (and its real twin) before the join. So copy
    # the actual winning first-pass row, identified by its unique Spectrum id.
    df = pl.read_csv(first_psm, separator="\t",
                     columns=["Spectrum", "Peptide", "Charge", "Intensity"])
    winner = (df.filter((pl.col("Peptide") == base) & (pl.col("Charge") == charge)
                        & (pl.col("Intensity") > 0))
                .sort("Intensity", descending=True).head(1))
    if winner.height == 0:
        raise RuntimeError(
            f"decoy injection: no first-pass winner for base={base} charge={charge}"
        )
    win_spec = winner["Spectrum"].item()

    for line in open(first_psm, errors="replace").read().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) > max(spec_i, prot) and parts[spec_i] == win_spec:
            parts[prot] = "rev_" + parts[prot]
            with open(first_psm, "a") as fo:
                fo.write("\t".join(parts) + "\n")
            return parts[prot]
    raise RuntimeError(f"decoy injection: winning line {win_spec} not found")


# --------------------------------------------------------------------------- #
# Build one fixture.
# --------------------------------------------------------------------------- #

def _run_step07(inp: dict[str, Path], out_ipc: Path, sample: str) -> pl.DataFrame:
    return cast("pl.DataFrame", analyze_outputs(
        first_psm_path=inp["first_psm"],
        second_psm_path=inp["second_psm"],
        ptmall_path=inp["ptmall"],
        psmrankall_path=inp["psmrankall"],
        pdv_path=inp["pdv"],
        output_ipc=out_ipc,
        sample=sample,
    ))


def build_fixture(ref: RefSpec) -> None:
    print(f"\n=== building fixture: {ref.name} ===")
    fx = L.FIXTURES_DIR / ref.name
    inp_dir, gold_dir = fx / "inputs", fx / "golden"
    inp_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)
    (fx / "reference").mkdir(parents=True, exist_ok=True)
    inp = L.fixture_inputs(ref.name)
    gold = L.fixture_golden(ref.name)

    slava = pl.read_ipc(ref.path("subs.ipc"))
    spectra = set(select_spectra(ref, slava))
    print(f"  selected {len(spectra)} spectra from {slava['Spectrum'].n_unique()} "
          f"reference spectra ({slava.height} rows)")

    # Slice inputs (spectrum_title == file:scan:charge is the key everywhere but
    # the two psm.tsv files, which need conversion / base matching).
    n_ptm = slice_headerless(ref.path("ptmall.txt"), inp["ptmall"], 3, spectra)
    n_pr = slice_with_header(ref.path("psmrankall.txt"), inp["psmrankall"], 3, spectra)
    import re
    suf = re.compile(r"_M(?:\d+(?:_\d+)*)C(?:\d+(?:_\d+)*)$")
    n_prb = slice_with_header(ref.path("psmrankall_base.txt"), inp["psmrankall_base"],
                              3, spectra, transform=lambda t: suf.sub("", t))
    n_pdv = slice_with_header(ref.path("pdv_spectra", "PDVExportResult.txt"),
                              inp["pdv"], 0, spectra)
    n_sec, bases = slice_second_psm(ref.path("second", "psm.tsv"),
                                    inp["second_psm"], spectra)
    n_fst = slice_first_psm(ref.path("psm.tsv"), inp["first_psm"], bases)
    n_mgf = slice_mgf(ref.path("mgfall.mgf"), inp["mgf"], spectra)
    print(f"  sliced rows: ptm={n_ptm} psmrank={n_pr} psmrank_base={n_prb} "
          f"pdv={n_pdv} second={n_sec} first={n_fst} mgf_blocks={n_mgf}")
    assert min(n_ptm, n_pr, n_pdv, n_sec, n_fst, n_mgf) > 0, \
        "a sliced input is empty - lineage broke (D-047)"

    # Step 7 golden.
    subs = _run_step07(inp, gold["subs"], ref.name)
    print(f"  step07 output: {subs.shape}")
    assert subs.height > 0, "step07 produced 0 rows on the slice (D-047)"

    # Optional decoy injection: rebuild and confirm the golden is unchanged and
    # the guard is genuinely exercised.
    if ref.inject_decoy:
        before = L.canonicalize(subs)
        rev_id = inject_decoy_row(inp["first_psm"], subs)
        subs = _run_step07(inp, gold["subs"], ref.name)
        L.assert_snapshot_equal(subs, before)  # dropped -> golden unchanged
        orig_drop = _s7._drop_decoy_rows
        _s7._drop_decoy_rows = lambda df: df
        try:
            bypassed = _run_step07(inp, gold_dir / "_decoy_probe.ipc", ref.name)
        finally:
            _s7._drop_decoy_rows = orig_drop
        (gold_dir / "_decoy_probe.ipc").unlink(missing_ok=True)
        n_rev = bypassed.filter(
            pl.col("Protein").cast(pl.Utf8).str.starts_with("rev_")
            | pl.col("Protein_right").cast(pl.Utf8).str.starts_with("rev_")
        ).height
        assert n_rev >= 1, "decoy injection did not produce a rev_ row"
        print(f"  injected decoy {rev_id!r}: dropped by current code, "
              f"{n_rev} rev_ row(s) would appear if 7502692 were reverted")

    # Commit a minimal Slava-reference projection for the eval's slava_compare
    # (so the test never reaches the cluster-only source).
    ref_proj = slava.filter(pl.col("Spectrum").is_in(list(spectra))).select(
        L.REFERENCE_COLUMNS
    )
    ref_proj.write_ipc(L.fixture_reference(ref.name))

    # Build-time gates: invariants + reference agreement (against the committed
    # projection, exactly what the test will use).
    L.run_all_invariants(subs)
    cmp = L.slava_compare(subs, ref_proj)
    cmp.assert_ok()
    print(f"  slava_compare: {cmp.n_matching_spectra}/{cmp.n_shared_spectra} "
          f"spectra identical, dpbp r={cmp.dpbp_pearson_r:.4f} "
          f"({cmp.n_dpbp_pairs} pairs)")

    # Step 11 golden.
    localized = localize(
        subs_ipc=gold["subs"],
        psmrankall_path=inp["psmrankall"],
        psmrankall_base_path=inp["psmrankall_base"],
        spectra_mgf=inp["mgf"],
        output_ipc=gold["subs_localized"],
        output_csv=gold["subs_localized_csv"],
    )
    print(f"  step11 output: {localized.shape}")
    assert localized.height > 0, (
        "step11 produced 0 localized rows - the slice lacks base-covered "
        "spectra; widen selection"
    )

    _write_readme(ref, fx, spectra, slava, subs, localized, cmp,
                  dict(ptm=n_ptm, psmrank=n_pr, psmrank_base=n_prb, pdv=n_pdv,
                       second=n_sec, first=n_fst, mgf=n_mgf))
    print(f"  wrote golden + README to {fx}")


def _write_readme(ref: RefSpec, fx: Path, spectra: set[str], slava: pl.DataFrame,
                  subs: pl.DataFrame, localized: pl.DataFrame,
                  cmp: L.SlavaComparison, counts: dict[str, int]) -> None:
    total_mb = sum(p.stat().st_size for p in (fx / "inputs").glob("*")) / 1e6
    decoy_note = (
        "\n## Injected reverse-decoy row\n\n"
        "`inputs/first_psm.tsv` carries **one synthetic `rev_`-prefixed row**, "
        "appended by the builder. Neither reference run produces a decoy leak "
        "naturally (their first-pass decoys never match a variant base in the "
        "join), so without this the `7502692` guard could never fire. The row "
        "duplicates a real first-pass PSM that joins into the golden, at an "
        "identical `first Intensity`, with its `Protein` renamed `rev_...`. "
        "Current code drops it, so `golden/subs.ipc` is unchanged; reverting the "
        "step07 decoy drop resurrects it and breaks both the `rev_`-count "
        "invariant and the snapshot.\n"
        if ref.inject_decoy else ""
    )
    text = f"""# Eval fixture: `{ref.name}`

Lineage-coherent slice of the reference TARSUS run at

    {ref.base}

Built by `scripts/build_eval_fixtures.py`. Do not hand-edit; re-bless with that
script. Total input size: ~{total_mb:.1f} MB.

## What this is

A {len(spectra)}-spectrum slice, every spectrum drawn from the run's Slava
reference `subs.ipc` so the reference-agreement invariants are meaningful. Each
step-07/11 input is filtered to exactly this spectrum set:

| input | rows kept |
|---|---|
| `ptmall.txt` | {counts['ptm']} |
| `psmrankall.txt` | {counts['psmrank']} |
| `psmrankall_base.txt` | {counts['psmrank_base']} |
| `pdv_export.txt` (from `pdv_spectra/PDVExportResult.txt`) | {counts['pdv']} |
| `second_psm.tsv` (from `second/psm.tsv`) | {counts['second']} |
| `first_psm.tsv` (from `psm.tsv`, kept by base) | {counts['first']} |
| `spectra.mgf` (from `mgfall.mgf`) | {counts['mgf']} blocks |

## Golden

- `golden/subs.ipc` - step07 output: **{subs.height} rows / {subs['spectrum_title'].n_unique()} spectra**.
- `golden/subs_localized.ipc` / `.csv` - step11 output: **{localized.height} rows**.

Produced by current (post-`7502692`) code. Regenerate on an intentional change
with `TARSUS_EVAL_UPDATE=1 uv run pytest tests/eval` (see `tests/eval/README.md`).

## Coverage (guards it exercises)

- Cys-origin and Met-origin substitutions - D-070 (`re.match` anchoring drop).
- I/L-ambiguous destination - the isobaric labelling path.
- multiple precursor charges.
{decoy_note}
## Reference agreement at build time

`slava_compare` vs the reference `subs.ipc`: {cmp.n_matching_spectra}/{cmp.n_shared_spectra}
shared spectra substitution-identical, dpbp Pearson r = {cmp.dpbp_pearson_r:.4f}.
"""
    (fx / "README.md").write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", choices=[*REFS, "all"], default="all")
    args = ap.parse_args()
    names = list(REFS) if args.fixture == "all" else [args.fixture]
    for name in names:
        build_fixture(REFS[name])
    print("\nDone.")


if __name__ == "__main__":
    main()
