"""Step 7 validation: SAV filtering against synthetic data."""

from pathlib import Path

import pytest

from src.tarsus.steps.step07_analyze_outputs import (
    load_ptm_details,
    filter_single_sav_psms,
    _parse_modification,
    _compute_expected_ions,
    _spectrum_to_title,
    _extract_base_name,
    analyze_outputs,
)
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
    assert ptm["origin"][0] == "A"  # Ala (1-letter)
    assert ptm["dest"][0] == "R"    # Arg (1-letter)
    assert ptm["mistranslatedPos"][0] == 2  # position - 1
    assert ptm["spectrum_title"][0] == "dev:1:2"


def test_step07_filter_single_sav_psms():
    """Filter single SAAV PSMs from loaded PTM data."""
    ptm = load_ptm_details(FIXTURES / "ptmall.txt")
    singles = filter_single_sav_psms(ptm)
    # With a single valid SAAV (PEPTIDE/Ala->Gly@1), should keep 1 row
    assert len(singles) == 1
    assert singles["spectrum_title"][0] == "dev:1:2"
    assert singles["ptm_score"][0] == 0.95


def test_step07_analyze_end_to_end(tmp_path):
    """Full analyze_outputs end-to-end with coherent FragPipe/PepQuery fixtures.

    The fixture is `PEPAIDE` with the candidate header `PEPAIDE_A3R`, i.e. A->R at
    0-based position 3 — and `PEPAIDE[3] == "A"`. That agreement is the point: Step 3b
    reads the residue *out of* the peptide when it writes the header, so in real data
    the header's origin letter and `base[pos]` always agree (verified: 0 mismatches on
    every non-I/L row across all four runs).

    It previously used `PEPTIDE` with the same `_A3R` header — but `PEPTIDE[3]` is
    `"T"`, not `"A"`. That incoherence was invisible while origin was taken from the
    header; it surfaced the moment origin started coming from `base` (D-065).
    """
    output_ipc = tmp_path / "subs.ipc"
    result = analyze_outputs(
        first_psm_path=FIXTURES / "first_psm.tsv",
        second_psm_path=FIXTURES / "second_psm.tsv",
        ptmall_path=FIXTURES / "ptmall.txt",
        psmrankall_path=FIXTURES / "psmrankall.txt",
        pdv_path=FIXTURES / "pdv_export.txt",
        output_ipc=output_ipc,
    )
    assert output_ipc.is_file()
    assert len(result) == 1
    assert result["dependent"][0] == "VARIANT"
    assert result["base"][0] == "PEPAIDE"
    # ORIGIN comes from `base[mistranslatedPos]`, NOT the candidate header — the
    # header carries the collapsed class `I` for the isobaric pair and would mislabel
    # every Leu origin as `I`. The origin is genome-known (D-065).
    pos = result["mistranslatedPos"][0]
    assert result["base"][0][pos] == "A"
    assert result["origin"][0] == "A"
    assert result["destination"][0] == "R"

    # SpectralSim/RTScore are carried verbatim out of the second-pass psm.tsv,
    # where FragPipe writes them when MSBooster runs — never recomputed, never
    # null-filled (D-069). They must land straight after `Delta Mass`.
    assert result["SpectralSim"][0] == 0.9789
    assert result["RTScore"][0] == 2.2396
    cols = result.columns
    assert cols[cols.index("Delta Mass") + 1] == "SpectralSim"
    assert cols[cols.index("Delta Mass") + 2] == "RTScore"

    # PDV fragment annotation, kept as PDV's raw bracketed strings under Slava's
    # names, positioned right after `Traced Scans` as in his GAPDH subs.ipc.
    assert result["ions"][0] == "[b4, b5]"
    assert result["ion_mz"][0] == "[404.2248, 517.3089]"
    assert result["ion_int"][0] == "[4588.39, 13457.61]"
    assert cols[cols.index("Traced Scans") + 1 : cols.index("Traced Scans") + 4] == [
        "ions", "ion_mz", "ion_int",
    ]


def test_step07_raises_when_msbooster_scores_absent(tmp_path):
    """A second-pass psm.tsv without the score columns means MSBooster was off.

    That run is not reference-faithful. Step 7 used to null-fill the columns,
    which kept the schema looking right while every value was null for an entire
    session (D-069) — so it must now fail loudly instead.
    """
    stripped = tmp_path / "second_psm_no_scores.tsv"
    src = (FIXTURES / "second_psm.tsv").read_text().splitlines()
    header = src[0].split("\t")
    drop = {header.index("SpectralSim"), header.index("RTScore")}
    stripped.write_text(
        "\n".join(
            "\t".join(f for i, f in enumerate(line.split("\t")) if i not in drop)
            for line in src
        )
        + "\n",
    )

    with pytest.raises(ValueError, match="MSBooster"):
        analyze_outputs(
            first_psm_path=FIXTURES / "first_psm.tsv",
            second_psm_path=stripped,
            ptmall_path=FIXTURES / "ptmall.txt",
            psmrankall_path=FIXTURES / "psmrankall.txt",
            pdv_path=FIXTURES / "pdv_export.txt",
            output_ipc=tmp_path / "subs.ipc",
        )
