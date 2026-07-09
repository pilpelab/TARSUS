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
    prepare_base_rescoring,
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
        df = pl.DataFrame({"spectrum_title": ["spec1"], "base": ["PEPTIDE"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(df, mgf_in, mgf_out, debug_unmatched=False)
        content = mgf_out.read_text()
        assert "TITLE=spec1_M0C0" in content
        assert "BEGIN IONS" in content
        assert "END IONS" in content

    def test_expands_mod_states(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self.make_mgf(mgf_in, ["spec1"])
        df = pl.DataFrame({"spectrum_title": ["spec1"], "base": ["PEMC"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(df, mgf_in, mgf_out, debug_unmatched=False)
        content = mgf_out.read_text()
        # PEMC has M at pos 3, C at pos 4 -> 4 mod states
        for suffix in ["M0C0", "M3C0", "M0C4", "M3C4"]:
            assert f"TITLE=spec1_{suffix}" in content, f"Missing suffix: {suffix}"

    def test_skips_unmatched(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self.make_mgf(mgf_in, ["spec1"])
        df = pl.DataFrame({"spectrum_title": ["unknown"], "base": ["PEPTIDE"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(df, mgf_in, mgf_out, debug_unmatched=False)
        content = mgf_out.read_text()
        assert content == ""

    def test_use_base_title(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self.make_mgf(mgf_in, ["file:100:2"])
        df = pl.DataFrame({"spectrum_title": ["file:100"], "base": ["PEPTIDE"]})
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
        df = pl.DataFrame({"spectrum_title": ["spec1"], "base": ["PEPTIDE"]})
        mgf_out = tmp_path / "out.mgf"
        expand_mgf_with_mod_states(df, mgf_in, mgf_out, debug_unmatched=False)
        assert mgf_out.read_text() == ""


class TestWriteDepSpectrumChunks:
    def test_writes_chunks(self, tmp_path: Path) -> None:
        df = pl.DataFrame({
            "base": ["PEP1", "PEP2"],
            "spectrum_title": ["spec1", "spec2"],
        })
        write_dep_spectrum_chunks(df, lines_per_file=1, out_dir=tmp_path)
        files = sorted(tmp_path.glob("variants_*.txt"))
        assert len(files) >= 1

    def test_chunk_size(self, tmp_path: Path) -> None:
        df = pl.DataFrame({
            "base": ["PEP1", "PEP2"],
            "spectrum_title": ["spec1", "spec2"],
        })
        write_dep_spectrum_chunks(df, lines_per_file=2, out_dir=tmp_path)
        files = sorted(tmp_path.glob("variants_*.txt"))
        assert len(files) == 1


class TestPrepareBaseRescoringLineage:
    """Regression: Step 8 must key on `spectrum_title`, not `Spectrum`.

    The reference `analyze_outputs.py` overwrites its `Spectrum` column with the
    converted `file:scan:charge` title, so `ref_validation_prep.py` reading
    `row["Spectrum"]` gets a title. Our Step 7 keeps `Spectrum` in FragPipe's raw
    `file_sub.scan.scan.charge` form and adds a separate `spectrum_title`.
    Reading `Spectrum` therefore matched 0 of 1,113 MGF titles and produced a
    0-byte mgfall_fakes.mgf, which Step 9 would then search for nothing.
    """

    def _mgf(self, path: Path, title: str) -> None:
        path.write_text(
            "BEGIN IONS\n"
            f"TITLE={title}\n"
            "PEPMASS=400.0\n"
            "CHARGE=2+\n"
            "100.0 10.0\n"
            "END IONS\n"
        )

    def _subs(self) -> pl.DataFrame:
        return pl.DataFrame({
            # raw FragPipe form — must NOT be used as the MGF key
            "Spectrum": ["f_sub.101063.101063.2"],
            "spectrum_title": ["f:101063:2"],
            "base": ["PEPTIDE"],
        })

    def test_matches_on_spectrum_title(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self._mgf(mgf_in, "f:101063:2")
        subs_ipc = tmp_path / "subs.ipc"
        self._subs().write_ipc(subs_ipc)

        mgf_out = tmp_path / "fakes.mgf"
        chunks = tmp_path / "chunks"
        prepare_base_rescoring(subs_ipc, mgf_in, mgf_out, chunks)

        assert mgf_out.stat().st_size > 0, "no spectra matched — wrong title column"
        assert "TITLE=f:101063:2_M0C0" in mgf_out.read_text()
        written = sorted(chunks.iterdir())
        assert written
        assert written[0].read_text().startswith("PEPTIDE\tf:101063:2_")

    def test_zero_matches_raises_instead_of_empty_mgf(self, tmp_path: Path) -> None:
        mgf_in = tmp_path / "in.mgf"
        self._mgf(mgf_in, "some:other:title")
        subs_ipc = tmp_path / "subs.ipc"
        self._subs().write_ipc(subs_ipc)

        with pytest.raises(RuntimeError, match="matched 0"):
            prepare_base_rescoring(
                subs_ipc, mgf_in, tmp_path / "fakes.mgf", tmp_path / "chunks",
            )
