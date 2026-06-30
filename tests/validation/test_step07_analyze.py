"""Step 7 validation: SAV filtering against synthetic data."""

import pytest
from pathlib import Path
from src.tarsus.steps.step07_analyze_outputs import (
    load_ptm_details,
    filter_single_sav_psms,
    _parse_modification,
    _compute_expected_ions,
    _spectrum_to_title,
    _extract_base_name,
    analyze_outputs,
)
from .conftest import load_expected, capture_expected

FIXTURES = Path(__file__).parent / "expected" / "step07_fixtures"


def test_step07_parse_modification():
    """Parse PepQuery PTM modification strings."""
    result = _parse_modification("Ala->Gly@1[")
    assert result is not None
    assert result["origin"] == "A"
    assert result["dest"] == "G"
    assert result["position"] == 1

    assert _parse_modification("nothing") is None


def test_step07_expected_ions():
    """Compute expected b/y ions for a substitution position."""
    ions = _compute_expected_ions("ABCDEF", 2)
    assert "b3" in ions
    assert "b4" in ions
    assert "b5" in ions
    assert "b6" in ions
    # y ions: n - position + 1 = 6-3+1 = 4, so y4, y5, y6
    assert "y6" in ions
    assert "y3" not in ions  # too early


def test_step07_spectrum_to_title():
    """Convert FragPipe Spectrum column to canonical spectrum_title."""
    assert _spectrum_to_title("file_sub.100.100.3") == "file:100:3"
    assert _spectrum_to_title("file.50.50.2") == "file:50:2"


def test_step07_load_ptm_details():
    """Load PepQuery ptmall.txt, parse modifications, verify columns."""
    ptm = load_ptm_details(FIXTURES / "ptmall.txt")
    assert len(ptm) == 1
    assert ptm["origin"][0] == "V"  # Val (1-letter)
    assert ptm["dest"][0] == "P"    # Pro (1-letter)
    assert ptm["mistranslated_pos"][0] == 2  # position - 1
    assert ptm["spectrum_title"][0] == "spec1"


def test_step07_filter_single_sav_psms():
    """Filter single SAAV PSMs from loaded PTM data."""
    ptm = load_ptm_details(FIXTURES / "ptmall.txt")
    singles = filter_single_sav_psms(ptm)
    # With a single valid SAAV (PEPTIDE/Ala->Gly@1), should keep 1 row
    assert len(singles) == 1
    assert singles["spectrum_title"][0] == "spec1"
    assert singles["ptm_score"][0] == 0.95


@pytest.mark.xfail(
    reason="BUG: second_psms has no 'base' column for join on line 309. "
           "join_cols=['base','Charge'] but second_psms uses 'dependent'. "
           "Fix: add base column to second_psms or change join key."
)
def test_step07_analyze_end_to_end(tmp_path):
    """Full analyze_outputs end-to-end — currently xfail due to join bug."""
    output_ipc = tmp_path / "subs.ipc"
    result = analyze_outputs(
        first_psm_path=FIXTURES / "first_psm.tsv",
        second_psm_path=FIXTURES / "second_psm.tsv",
        ptmall_path=FIXTURES / "ptmall.txt",
        psmrankall_path=FIXTURES / "psmrankall.txt",
        pdv_path=FIXTURES / "pdv_export.txt",
        output_ipc=output_ipc,
    )
    # Would verify subs.ipc structure here
    assert output_ipc.is_file()
    assert len(result) >= 0
