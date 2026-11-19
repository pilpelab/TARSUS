"""TARSUS master orchestration — runs on LSF compute node.

Entry point: python -m tarsus.orchestration <outdir> <fasta> <raw...>

Chains all 11 pipeline steps on the compute node. Heavy-tool steps
submit child bsub jobs and wait; Python analysis steps run inline.

Sentinel checkpointing: each step writes a .done marker after successful
completion.  On re-run (e.g. after a crash), completed steps are skipped.
Delete the .done file to force a step to re-run.
"""

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any


def _log(step: str, msg: str = "") -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {step}: {msg}")


def _skip_if_done(sentinel: Path, label: str) -> bool:
    """Return True if *sentinel* exists (step already completed)."""
    if sentinel.exists():
        _log(label, "SKIP — already complete (.done)")
        return True
    return False


def run_pipeline(
    outdir: Path, fasta: Path, raw_files: list[Path],
    cds_fasta: Path | None = None,
    localize_tol: float | None = None,
    msbooster_models: str = "best",
) -> None:
    """Execute the full TARSUS pipeline with checkpoint resumption.

    Args:
        cds_fasta: CDS (nucleotide) FASTA. Optional; only Step 12's 61x19 codon
            heatmap needs it. Absent -> that one figure is skipped, loudly.
        localize_tol: Step 11 PyAscore fragment tolerance in Da. ``None`` uses
            ``step11_localize.DEFAULT_LOCALIZE_TOL_DA`` (0.01, Slava's value).
        msbooster_models: Step 3a MSBooster model selection, ``best`` (Koina
            find-best, Slava's setting) or ``dia-nn`` (offline local models).
    """
    from tarsus.env import ToolEnvironment

    tool_env = ToolEnvironment.from_env()

    _log("INIT", f"Output: {outdir}")
    _log("INIT", f"FASTA:  {fasta}")
    _log("INIT", f"CDS:    {cds_fasta or '(none — 61x19 codon heatmap will be skipped)'}")
    _log("INIT", f"Localize tol: {localize_tol if localize_tol is not None else 'default'} Da")
    _log("INIT", f"MSBooster models: {msbooster_models}")
    _log("INIT", f"Files:  {len(raw_files)} raw file(s)")
    for f in raw_files:
        _log("INIT", f"  {f.name}")

    # ── Step 1: Convert .raw → .mzML ─────────────────────────────────
    _s1 = outdir / "01_mzml" / ".done"
    if not _skip_if_done(_s1, "S01"):
        _log("S01", "Converting .raw → .mzML (LSF)")
        from tarsus.steps.step01_convert import step01_convert
        step01_convert(raw_files, outdir / "01_mzml", tool_env, local=False)
        _s1.touch()
        _log("S01", "Done")

    # ── Step 2: PepQuery index from the original mzML ────────────────
    # Must index 01_mzml/, not 03a_first_pass/*_sub.mzML: PepQuery titles
    # spectra after the file it indexed, and Steps 4/7 both address spectra as
    # `file:scan:charge` with no `_sub` suffix. Indexing the _sub remainder
    # shifts the title namespace and silently zeroes Step 7 (D-047).
    _s2 = outdir / "02_index" / ".done"
    if not _skip_if_done(_s2, "S02"):
        _log("S02", "Building PepQuery index from original mzML (LSF)")
        from tarsus.steps.step02_make_index import step02_make_index
        step02_make_index(outdir / "01_mzml", outdir / "02_index", tool_env)
        _s2.touch()
        _log("S02", "Done")

    # ── Step 3a: FragPipe first pass ─────────────────────────────────
    _s3a = outdir / "03a_first_pass" / ".done"
    if not _skip_if_done(_s3a, "S03a"):
        _log("S03a", "FragPipe first-pass search (LSF)")
        from tarsus.steps.step03a_first_pass import step03a_first_pass
        step03a_first_pass(fasta, outdir / "01_mzml", outdir / "03a_first_pass", tool_env,
                           msbooster_models=msbooster_models)
        _s3a.touch()
        _log("S03a", "Done")

    # ── Step 3b: In-silico mutagenesis ───────────────────────────────
    _s3b = outdir / "03b_candidates" / ".done"
    if not _skip_if_done(_s3b, "S03b"):
        _log("S03b", "Generating variant peptide candidates")
        from tarsus.steps.step03b_make_peptides import make_peptide_candidates
        make_peptide_candidates(
            peptide_tsv=outdir / "03a_first_pass" / "peptide.tsv",
            output_fasta=outdir / "03b_candidates" / "pep_candidates.fa",
        )
        _s3b.touch()
        _log("S03b", "Done")

    # ── Step 3c: FragPipe second pass ────────────────────────────────
    _s3c = outdir / "03c_second_pass" / ".done"
    if not _skip_if_done(_s3c, "S03c"):
        _log("S03c", "FragPipe second-pass search (LSF)")
        from tarsus.steps.step03c_second_pass import step03c_second_pass
        step03c_second_pass(
            mzml_dir=outdir / "03a_first_pass",  # uses *_sub.mzML (unidentified spectra)
            pep_candidates=outdir / "03b_candidates" / "pep_candidates.fa",
            output_dir=outdir / "03c_second_pass",
            tool_env=tool_env,
        )
        _s3c.touch()
        _log("S03c", "Done")

    # ── Step 4: Extract PSM for PepQuery ─────────────────────────────
    _s4 = outdir / "04_psm_input" / ".done"
    if not _skip_if_done(_s4, "S04"):
        _log("S04", "Extracting PSM data for PepQuery")
        from tarsus.steps.step04_extract_psm import extract_psm
        (outdir / "04_psm_input").mkdir(parents=True, exist_ok=True)
        extract_psm(
            psm_path=outdir / "03c_second_pass" / "second" / "psm.tsv",
            output_path=outdir / "04_psm_input" / "psm_input4pepquery.tsv",
        )
        _s4.touch()
        _log("S04", "Done")

    # ── Step 5: PepQuery validation ──────────────────────────────────
    _s5 = outdir / "05_pepquery" / ".done"
    if not _skip_if_done(_s5, "S05"):
        _log("S05", "Running PepQuery validation (LSF)")
        from tarsus.steps.step05_query_psm import step05_query_psm
        step05_query_psm(
            psm_input=outdir / "04_psm_input" / "psm_input4pepquery.tsv",
            index_dir=outdir / "02_index" / "pepquery_index",
            output_dir=outdir / "05_pepquery",
            tool_env=tool_env,
            fasta_path=fasta,
        )
        _s5.touch()
        _log("S05", "Done")

    # ── Step 6: Aggregate + PDV ──────────────────────────────────────
    _s6 = outdir / "06_aggregated" / ".done"
    if not _skip_if_done(_s6, "S06"):
        _log("S06", "Aggregating PepQuery results + PDV")
        from tarsus.steps.step06_aggregate_query import step06_aggregate_query
        step06_aggregate_query(
            result_dir=outdir / "05_pepquery" / "pepquery_result",
            output_dir=outdir / "06_aggregated",
            tool_env=tool_env,
        )
        _s6.touch()
        _log("S06", "Done")

    # ── Step 7: Analyze outputs ──────────────────────────────────────
    _s7 = outdir / "07_analyze" / ".done"
    if not _skip_if_done(_s7, "S07"):
        _log("S07", "Filtering confident SAAVs")
        from tarsus.steps.step07_analyze_outputs import analyze_outputs
        _07_out = outdir / "07_analyze"
        _07_out.mkdir(parents=True, exist_ok=True)
        analyze_outputs(
            first_psm_path=outdir / "03a_first_pass" / "psm.tsv",
            second_psm_path=outdir / "03c_second_pass" / "second" / "psm.tsv",
            ptmall_path=outdir / "06_aggregated" / "ptmall.txt",
            psmrankall_path=outdir / "06_aggregated" / "psmrankall.txt",
            pdv_path=outdir / "06_aggregated" / "pdv_spectra" / "PDVExportResult.txt",
            output_ipc=_07_out / "subs.ipc",
            sample=outdir.name,
        )
        _s7.touch()
        _log("S07", f"Done → {_07_out / 'subs.ipc'}")

    # Guardrail: Step 7 stamps .done even when it filters everything away, so a
    # spectrum-title/peptide lineage break would otherwise surface much later as
    # a confusing Step 8 error. Check the row count directly, outside the .done
    # branch, so resumed runs are validated too (D-047).
    _subs_ipc = outdir / "07_analyze" / "subs.ipc"
    import polars as _pl
    _subs_rows = _pl.read_ipc(_subs_ipc).height
    if _subs_rows == 0:
        raise RuntimeError(
            f"Step 7 produced 0 candidate rows in {_subs_ipc}. Steps 8-11 were "
            "not run. This almost always means a spectrum-title lineage break "
            "between FragPipe (Step 3c), PepQuery (Steps 4/5) and the Step 2 "
            "index — verify that Step 2 indexed the original mzML and that "
            "Step 4 emitted two columns. See D-047 in .memory/decisions.md."
        )
    _log("S07", f"{_subs_rows} candidate SAAV rows")

    # ── Step 8: Reference validation prep ────────────────────────────
    _s8 = outdir / "08_base_input" / ".done"
    if not _skip_if_done(_s8, "S08"):
        _log("S08", "Preparing reference validation inputs")
        from tarsus.steps.step08_ref_validation_prep import prepare_base_rescoring
        _08_out = outdir / "08_base_input"
        _08_out.mkdir(parents=True, exist_ok=True)
        prepare_base_rescoring(
            subs_ipc=outdir / "07_analyze" / "subs.ipc",
            mgf_in=outdir / "06_aggregated" / "mgfall.mgf",
            mgf_out=_08_out / "mgfall_fakes.mgf",
            pepquery_input_dir=_08_out / "pepquery_input_base",
        )
        _s8.touch()
        _log("S08", "Done")

    # Guardrail: Step 8 should create at least one base-rescoring input chunk
    # for any non-empty Step 7 result. If it creates none, stop loudly rather
    # than stamping Steps 9-11 as complete with missing/empty outputs — that can
    # hide upstream lineage/filtering bugs.
    base_input_dir = outdir / "08_base_input" / "pepquery_input_base"
    if not any(base_input_dir.iterdir()):
        raise RuntimeError(
            f"Step 8 produced no base-rescoring input files in {base_input_dir}. "
            "Downstream Steps 9-11 were not run. Inspect Step 7 candidate "
            "counts and spectrum-title/peptide lineage before marking the "
            "pipeline complete."
        )

    # ── Step 9: PepQuery base rescoring ──────────────────────────────
    _s9 = outdir / "09_pepquery_base" / ".done"
    if not _skip_if_done(_s9, "S09"):
        _log("S09", "Running PepQuery base rescoring (LSF)")
        from tarsus.steps.step09_query_psm_base import step09_query_psm_base
        step09_query_psm_base(
            input_dir=outdir / "08_base_input" / "pepquery_input_base",
            index_dir=outdir / "02_index" / "pepquery_index",
            mgf_path=outdir / "08_base_input" / "mgfall_fakes.mgf",
            output_dir=outdir / "09_pepquery_base",
            tool_env=tool_env,
            fasta_path=fasta,
        )
        _s9.touch()
        _log("S09", "Done")

    # ── Step 10: Aggregate base results ──────────────────────────────
    _s10 = outdir / "10_aggregated_base" / ".done"
    if not _skip_if_done(_s10, "S10"):
        _log("S10", "Aggregating base rescoring results")
        from tarsus.steps.step10_aggregate_query_base import step10_aggregate_query_base
        step10_aggregate_query_base(
            result_dir=outdir / "09_pepquery_base" / "pepquery_result_recheck_base",
            output_dir=outdir / "10_aggregated_base",
            tool_env=tool_env,
        )
        _s10.touch()
        _log("S10", "Done")

    # ── Step 11: Localize substitutions ──────────────────────────────
    _s11 = outdir / "11_localized" / ".done"
    if not _skip_if_done(_s11, "S11"):
        _log("S11", "Localizing substitutions (PyAscore)")
        from tarsus.steps.step11_localize import localize
        _11_out = outdir / "11_localized"
        _11_out.mkdir(parents=True, exist_ok=True)
        _tol_kw = {} if localize_tol is None else {"precursor_tol": localize_tol}
        localize(
            subs_ipc=outdir / "07_analyze" / "subs.ipc",
            psmrankall_path=outdir / "06_aggregated" / "psmrankall.txt",
            psmrankall_base_path=outdir / "10_aggregated_base" / "psmrankall_base.txt",
            spectra_mgf=outdir / "06_aggregated" / "mgfall.mgf",
            output_ipc=_11_out / "subs_localized.ipc",
            output_csv=_11_out / "subs_localized.csv",
            **_tol_kw,
        )
        _s11.touch()
        _log("S11", f"Done → {_11_out / 'subs_localized.csv'}")

    _s12 = outdir / "12_visualize" / ".done"
    if not _skip_if_done(_s12, "S12"):
        _log("S12", "Generating SAAV visualizations")
        from tarsus.steps.step12_visualize import step12_visualize
        _12_out = outdir / "12_visualize"
        _12_out.mkdir(parents=True, exist_ok=True)
        step12_visualize(
            localized_ipc=outdir / "11_localized" / "subs_localized.ipc",
            output_dir=outdir,
            cds_fasta=cds_fasta,
        )
        _s12.touch()
        _log("S12", f"Done → {_12_out}/")

    _log("DONE", "Pipeline complete.")


def _parse_master_argv(argv: list[str]) -> tuple[Path, Path, list[Path], dict[str, Any]]:
    """Parse the master job's argv: optional flags, then outdir, fasta, *raw_files.

    Optional ``--flag value`` pairs must be stripped before the positionals, which
    are variadic. Returns ``(outdir, fasta, raw_files, run_pipeline_kwargs)``.

    Raises:
        ValueError: a flag is missing its value or fewer than 3 positionals remain.
    """
    args = list(argv)
    kwargs: dict[str, Any] = {}
    flags: dict[str, tuple[str, Callable[[str], Any]]] = {
        "--cds": ("cds_fasta", Path),
        "--localize-tol": ("localize_tol", float),
        "--msbooster-models": ("msbooster_models", str),
    }
    for flag, (key, convert) in flags.items():
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                raise ValueError(f"{flag} given without a value")
            kwargs[key] = convert(args[i + 1])
            del args[i:i + 2]
    if len(args) < 3:
        raise ValueError(f"expected outdir, fasta and >=1 raw file, got {args!r}")
    return Path(args[0]), Path(args[1]), [Path(f) for f in args[2:]], kwargs


def main(argv: list[str]) -> None:
    """Master job entry point: group-readable umask, then the pipeline."""
    from .lsf import use_group_readable_umask

    use_group_readable_umask()
    outdir, fasta, raw_files, kwargs = _parse_master_argv(argv)
    run_pipeline(outdir, fasta, raw_files, **kwargs)


if __name__ == "__main__":
    main(sys.argv[1:])
