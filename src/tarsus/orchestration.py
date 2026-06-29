"""TARSUS master orchestration — runs on LSF compute node.

Entry point: python -m tarsus.orchestration <outdir> <fasta> <raw...>

Chains all 11 pipeline steps on the compute node. Heavy-tool steps
submit child bsub jobs and wait; Python analysis steps run inline.
"""

import sys
from datetime import datetime
from pathlib import Path


def _log(step: str, msg: str = "") -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {step}: {msg}")


def run_pipeline(outdir: Path, fasta: Path, raw_files: list[Path]) -> None:
    """Execute the full TARSUS pipeline."""
    from tarsus.env import ToolEnvironment

    tool_env = ToolEnvironment.from_env()

    _log("INIT", f"Output: {outdir}")
    _log("INIT", f"FASTA:  {fasta}")
    _log("INIT", f"Files:  {len(raw_files)} raw file(s)")
    for f in raw_files:
        _log("INIT", f"  {f.name}")

    # ── Step 1: Convert .raw → .mzML ─────────────────────────────────
    _log("S01", "Converting .raw → .mzML (LSF)")
    from tarsus.steps.step01_convert import step01_convert
    step01_convert(raw_files, outdir / "01_mzml", tool_env, local=False)
    _log("S01", "Done")

    # ── Step 2: PepQuery index ───────────────────────────────────────
    _log("S02", "Building PepQuery index (LSF)")
    from tarsus.steps.step02_make_index import step02_make_index
    step02_make_index(outdir / "01_mzml", outdir / "02_index", tool_env)
    _log("S02", "Done")

    # ── Step 3a: FragPipe first pass ─────────────────────────────────
    _log("S03a", "FragPipe first-pass search (LSF)")
    from tarsus.steps.step03a_first_pass import step03a_first_pass
    step03a_first_pass(fasta, outdir / "01_mzml", outdir / "03a_first_pass", tool_env)
    _log("S03a", "Done")

    # ── Step 3b: In-silico mutagenesis ───────────────────────────────
    _log("S03b", "Generating variant peptide candidates")
    from tarsus.steps.step03b_make_peptides import make_peptide_candidates
    make_peptide_candidates(
        peptide_tsv=outdir / "03a_first_pass" / "peptide.tsv",
        output_fasta=outdir / "03b_candidates" / "pep_candidates.fa",
    )
    _log("S03b", "Done")

    # ── Step 3c: FragPipe second pass ────────────────────────────────
    _log("S03c", "FragPipe second-pass search (LSF)")
    from tarsus.steps.step03c_second_pass import step03c_second_pass
    step03c_second_pass(
        mzml_dir=outdir / "01_mzml",
        pep_candidates=outdir / "03b_candidates" / "pep_candidates.fa",
        output_dir=outdir / "03c_second_pass",
        tool_env=tool_env,
    )
    _log("S03c", "Done")

    # ── Step 4: Extract PSM for PepQuery ─────────────────────────────
    _log("S04", "Extracting PSM data for PepQuery")
    from tarsus.steps.step04_extract_psm import extract_psm
    (outdir / "04_psm_input").mkdir(parents=True, exist_ok=True)
    extract_psm(
        psm_path=outdir / "03c_second_pass" / "second" / "psm.tsv",
        output_path=outdir / "04_psm_input" / "psm_input4pepquery.tsv",
    )
    _log("S04", "Done")

    # ── Step 5: PepQuery validation ──────────────────────────────────
    _log("S05", "Running PepQuery validation (LSF)")
    from tarsus.steps.step05_query_psm import step05_query_psm
    step05_query_psm(
        psm_input=outdir / "04_psm_input" / "psm_input4pepquery.tsv",
        index_dir=outdir / "02_index" / "pepquery_index",
        output_dir=outdir / "05_pepquery",
        tool_env=tool_env,
    )
    _log("S05", "Done")

    # ── Step 6: Aggregate + PDV ──────────────────────────────────────
    _log("S06", "Aggregating PepQuery results + PDV")
    from tarsus.steps.step06_aggregate_query import step06_aggregate_query
    step06_aggregate_query(
        result_dir=outdir / "05_pepquery" / "pepquery_result",
        output_dir=outdir / "06_aggregated",
        tool_env=tool_env,
    )
    _log("S06", "Done")

    # ── Step 7: Analyze outputs ──────────────────────────────────────
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
    _log("S07", f"Done → {_07_out / 'subs.ipc'}")

    # ── Step 8: Reference validation prep ────────────────────────────
    _log("S08", "Preparing reference validation inputs")
    from tarsus.steps.step08_ref_validation_prep import prepare_base_rescoring
    _08_out = outdir / "08_base_input"
    _08_out.mkdir(parents=True, exist_ok=True)
    prepare_base_rescoring(
        subs_ipc=_07_out / "subs.ipc",
        mgf_in=outdir / "06_aggregated" / "mgfall.mgf",
        mgf_out=_08_out / "mgfall_fakes.mgf",
        pepquery_input_dir=_08_out / "pepquery_input_base",
    )
    _log("S08", "Done")

    # ── Step 9: PepQuery base rescoring ──────────────────────────────
    _log("S09", "Running PepQuery base rescoring (LSF)")
    from tarsus.steps.step09_query_psm_base import step09_query_psm_base
    step09_query_psm_base(
        input_dir=_08_out / "pepquery_input_base",
        index_dir=outdir / "02_index" / "pepquery_index",
        mgf_path=_08_out / "mgfall_fakes.mgf",
        output_dir=outdir / "09_pepquery_base",
        tool_env=tool_env,
    )
    _log("S09", "Done")

    # ── Step 10: Aggregate base results ──────────────────────────────
    _log("S10", "Aggregating base rescoring results")
    from tarsus.steps.step10_aggregate_query_base import step10_aggregate_query_base
    step10_aggregate_query_base(
        result_dir=outdir / "09_pepquery_base" / "pepquery_result_recheck_base",
        output_dir=outdir / "10_aggregated_base",
        tool_env=tool_env,
    )
    _log("S10", "Done")

    # ── Step 11: Localize substitutions ──────────────────────────────
    _log("S11", "Localizing substitutions (PyAscore)")
    from tarsus.steps.step11_localize import localize
    _11_out = outdir / "11_localized"
    _11_out.mkdir(parents=True, exist_ok=True)
    localize(
        subs_ipc=_07_out / "subs.ipc",
        psmrankall_path=outdir / "06_aggregated" / "psmrankall.txt",
        psmrankall_base_path=outdir / "10_aggregated_base" / "psmrankall_base.txt",
        spectra_mgf=outdir / "06_aggregated" / "mgfall.mgf",
        output_ipc=_11_out / "subs_localized.ipc",
        output_csv=_11_out / "subs_localized.csv",
    )
    _log("S11", f"Done → {_11_out / 'subs_localized.csv'}")

    _log("DONE", "Pipeline complete.")


if __name__ == "__main__":
    outdir = Path(sys.argv[1])
    fasta = Path(sys.argv[2])
    raw_files = [Path(f) for f in sys.argv[3:]]
    run_pipeline(outdir, fasta, raw_files)
