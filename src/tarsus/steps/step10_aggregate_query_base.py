"""Step 10: Aggregate PepQuery base rescoring results.

Identical in logic to Step 6, but writes to _base suffixed output files.
"""

from pathlib import Path
from ..env import ToolEnvironment


def step10_aggregate_query_base(
    result_dir: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    java_heap_mb: int = 4096,
) -> Path:
    """Concatenate base rescoring PepQuery results.

    Args:
        result_dir: pepquery_result_recheck_base/ from Step 9.
        output_dir: Output directory for aggregated files.
        tool_env: Resolved tool environment.

    Returns:
        Path to output directory.
    """
    if not result_dir.is_dir():
        raise FileNotFoundError(
            f"Base rescoring result directory not found: {result_dir}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. psmrankall_base.txt
    rank_files = sorted(result_dir.rglob("psm_rank.txt"))
    if not rank_files:
        raise RuntimeError(f"No psm_rank.txt files found in {result_dir}")

    psmrankall = output_dir / "psmrankall_base.txt"
    data_rows = 0
    with psmrankall.open("w") as out:
        for i, f in enumerate(rank_files):
            content = f.read_text()
            lines = content.split("\n")
            if i > 0 and lines:
                lines = lines[1:]
            data_rows += sum(1 for ln in lines[1 if i == 0 else 0:] if ln.strip())
            out.write("\n".join(lines) + "\n")

    # Guardrail: Step 11 inner-joins psmrankall_base.txt to decide which variants
    # outscore their reference peptide. With zero data rows that join drops every
    # candidate and subs_localized.csv silently comes out empty.
    if data_rows == 0:
        raise RuntimeError(
            f"Step 10 aggregated {len(rank_files)} psm_rank.txt files from "
            f"{result_dir} but found no data rows, so {psmrankall} has only a "
            f"header. Step 11 would then localize nothing. Check that Step 9's "
            f"PepQuery base rescoring actually matched spectra."
        )

    # 2. ptmall_base.txt
    ptm_files = sorted(result_dir.rglob("ptm_detail.txt"))
    if ptm_files:
        ptmall = output_dir / "ptmall_base.txt"
        with ptmall.open("w") as out:
            for i, f in enumerate(ptm_files):
                content = f.read_text()
                lines = content.split("\n")
                if i > 0 and lines:
                    lines = lines[1:]
                out.write("\n".join(lines) + "\n")

    # 3. mgfall_base.mgf
    mgf_files = sorted(result_dir.rglob("psm_rank.mgf"))
    if mgf_files:
        mgfall = output_dir / "mgfall_base.mgf"
        with mgfall.open("w") as out:
            for f in mgf_files:
                out.write(f.read_text() + "\n")

    return output_dir
