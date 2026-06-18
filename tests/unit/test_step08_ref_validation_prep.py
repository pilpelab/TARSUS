"""Unit tests for Step 8 — reference validation preparation."""

from pathlib import Path
import polars as pl
import pytest
from src.tarsus.steps.step08_ref_validation_prep import (
    peptide_mz_all_states,
    mod_suffixes_for_seq,
    _canon_title,
    expand_mgf_with_mod_states,
    write_dep_spectrum_chunks,
)


class TestPeptideMzAllStates:
    def test_no_m_no_c(self) -> None:
        result = peptide_mz_all_states("PEPTIDE", 2)
        assert "M0C0" in result
        assert len(result) == 1
        assert result["M0C0"] > 0

    def test_single_methionine(self) -> None:
        result = peptide_mz_all_states("PEPTIMDE", 2)
        assert "M0C0" in result
        assert "M6C0" in result
        assert len(result) == 2
        assert result["M6C0"] > result["M0C0"]

    def test_methionine_and_cysteine(self) -> None:
        result = peptide_mz_all_states("PEMC", 2)
        assert len(result) == 4  # M0C0, M3C0, M0C4, M3C4
        assert "M0C0" in result
        assert "M3C0" in result
        assert "M0C4" in result
        assert "M3C4" in result

    def test_charge_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            peptide_mz_all_states("PEP", 0)

    def test_charge_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            peptide_mz_all_states("PEP", -1)

    def test_unknown_aa_raises(self) -> None:
        import pytest
        with pytest.raises(ValueError):
            peptide_mz_all_states("PEX", 2)


class TestModSuffixesForSeq:
    def test_no_m_c(self) -> None:
        assert mod_suffixes_for_seq("PEPTIDE") == ["M0C0"]

    def test_only_m(self) -> None:
        suffixes = mod_suffixes_for_seq("PEPTIMDE")
        assert set(suffixes) == {"M0C0", "M6C0"}

    def test_only_c(self) -> None:
        suffixes = mod_suffixes_for_seq("PEPCTIDE")
        assert set(suffixes) == {"M0C0", "M0C4"}

    def test_both_m_and_c(self) -> None:
        suffixes = mod_suffixes_for_seq("PEMC")
        assert set(suffixes) == {"M0C0", "M3C0", "M0C4", "M3C4"}

    def test_multiple_m(self) -> None:
        suffixes = mod_suffixes_for_seq("MEMAM")
        # 3 M's -> 8 states, no C -> 1 state
        assert len(suffixes) == 8


class TestCanonTitle:
    def test_normalizes_trailing(self) -> None:
        assert _canon_title("file:100:2", use_base=True) == "file:100"

    def test_no_colon(self) -> None:
        assert _canon_title("file100", use_base=True) == "file100"

    def test_no_normalize(self) -> None:
        assert _canon_title("file:100:2", use_base=False) == "file:100:2"


class TestExpandMgfWithModStates:
    def make_mgf(self, path: Path, titles: list[str]) -> None:
        lines: list[str] = []
        for t in titles:
            lines.extend([
                "BEGIN IONS\n",
                f"TITLE={t}\n",
                "PEPMASS=500.0\n",
                "CHARGE=2+\n",
                "1.0 100.0\n",
                "END IONS\n",
            ])
        path.write_text("".join(lines))

    def test_expands_single_spectrum(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self.make_mgf(mgf_in, ["spec1"])
        df = pl.DataFrame({"Spectrum": ["spec1"], "base": ["PEPTIDE"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(df, mgf_in, mgf_out, debug_unmatched=False)
        content = mgf_out.read_text()
        assert "TITLE=spec1_M0C0" in content
        assert "BEGIN IONS" in content
        assert "END IONS" in content

    def test_expands_mod_states(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self.make_mgf(mgf_in, ["spec1"])
        df = pl.DataFrame({"Spectrum": ["spec1"], "base": ["PEMC"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(df, mgf_in, mgf_out, debug_unmatched=False)
        content = mgf_out.read_text()
        # PEMC has M at pos 3, C at pos 4 -> 4 mod states
        for suffix in ["M0C0", "M3C0", "M0C4", "M3C4"]:
            assert f"TITLE=spec1_{suffix}" in content, f"Missing suffix: {suffix}"

    def test_skips_unmatched(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self.make_mgf(mgf_in, ["spec1"])
        df = pl.DataFrame({"Spectrum": ["unknown"], "base": ["PEPTIDE"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(df, mgf_in, mgf_out, debug_unmatched=False)
        content = mgf_out.read_text()
        assert content == ""

    def test_use_base_title(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self.make_mgf(mgf_in, ["file:100:2"])
        df = pl.DataFrame({"Spectrum": ["file:100"], "base": ["PEPTIDE"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(
            df, mgf_in, mgf_out,
            use_base_title=True, debug_unmatched=False,
        )
        content = mgf_out.read_text()
        assert "TITLE=file:100_M0C0" in content

    def test_missing_charge_skips(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        mgf_in.write_text(
            "BEGIN IONS\nTITLE=spec1\nPEPMASS=500.0\n1.0 100.0\nEND IONS\n",
        )
        df = pl.DataFrame({"Spectrum": ["spec1"], "base": ["PEPTIDE"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(df, mgf_in, mgf_out, debug_unmatched=False)
        assert mgf_out.read_text() == ""


class TestWriteDepSpectrumChunks:
    def test_writes_chunks(self, tmp_path: Path) -> None:
        df = pl.DataFrame({
            "base": ["PEP1", "PEP2"],
            "Spectrum": ["spec1", "spec2"],
        })
        write_dep_spectrum_chunks(df, lines_per_file=1, out_dir=tmp_path)
        files = sorted(tmp_path.glob("variants_*.txt"))
        assert len(files) >= 1

    def test_chunk_size(self, tmp_path: Path) -> None:
        df = pl.DataFrame({
            "base": ["PEP1", "PEP2"],
            "Spectrum": ["spec1", "spec2"],
        })
        write_dep_spectrum_chunks(df, lines_per_file=2, out_dir=tmp_path)
        files = sorted(tmp_path.glob("variants_*.txt"))
        assert len(files) == 1
