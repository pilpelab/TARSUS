"""TARSUS master orchestration — runs on LSF compute node.

Entry point: python -m tarsus.orchestration <outdir> <fasta> <raw...>

Chains all 11 pipeline steps on the compute node. Heavy-tool steps
submit child bsub jobs and wait; Python analysis steps run inline.

Sentinel checkpointing: each step writes a .done marker after successful
completion.  On re-run (e.g. after a crash), completed steps are skipped.
Delete the .done file to force a step to re-run.
"""

import sys
from datetime import datetime
from pathlib import Path


def _log(step: str, msg: str = "") -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {step}: {msg}")


def _skip_if_done(sentinel: Path, label: str) -> bool:
    """Return True if *sentinel* exists (step already completed)."""
    if sentinel.exists():
        _log(label, "SKIP — already complete (.done)")
        return True
    return False


def run_pipeline(outdir: Path, fasta: Path, raw_files: list[Path]) -> None:
    """Execute the full TARSUS pipeline with checkpoint resumption."""
    from tarsus.env import ToolEnvironment

    tool_env = ToolEnvironment.from_env()

    _log("INIT", f"Output: {outdir}")
    _log("INIT", f"FASTA:  {fasta}")
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

    # ── Step 2: PepQuery index ───────────────────────────────────────
    _s2 = outdir / "02_index" / ".done"
    if not _skip_if_done(_s2, "S02"):
        _log("S02", "Building PepQuery index (LSF)")
        from tarsus.steps.step02_make_index import step02_make_index
        step02_make_index(outdir / "01_mzml", outdir / "02_index", tool_env)
        _s2.touch()
        _log("S02", "Done")

    # ── Step 3a: FragPipe first pass ─────────────────────────────────
    _s3a = outdir / "03a_first_pass" / ".done"
    if not _skip_if_done(_s3a, "S03a"):
        _log("S03a", "FragPipe first-pass search (LSF)")
        from tarsus.steps.step03a_first_pass import step03a_first_pass
        step03a_first_pass(fasta, outdir / "01_mzml", outdir / "03a_first_pass", tool_env)
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
            mzml_dir=outdir / "01_mzml",
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
        )
        _s7.touch()
        _log("S07", f"Done → {_07_out / 'subs.ipc'}")

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
        localize(
            subs_ipc=outdir / "07_analyze" / "subs.ipc",
            psmrankall_path=outdir / "06_aggregated" / "psmrankall.txt",
            psmrankall_base_path=outdir / "10_aggregated_base" / "psmrankall_base.txt",
            spectra_mgf=outdir / "06_aggregated" / "mgfall.mgf",
            output_ipc=_11_out / "subs_localized.ipc",
            output_csv=_11_out / "subs_localized.csv",
        )
        _s11.touch()
        _log("S11", f"Done → {_11_out / 'subs_localized.csv'}")

    _log("DONE", "Pipeline complete.")


if __name__ == "__main__":
    outdir = Path(sys.argv[1])
    fasta = Path(sys.argv[2])
    raw_files = [Path(f) for f in sys.argv[3:]]
    run_pipeline(outdir, fasta, raw_files)
