"""Unit tests for Step 3c — FragPipe second-pass (nocleavage)."""

import re
from pathlib import Path

import pytest

from src.tarsus.assets import WORKFLOW_TEMPLATE
from src.tarsus.env import ToolEnvironment
from src.tarsus.steps.step03c_second_pass import (
    GENERATED_SECOND_PASS_WORKFLOW,
    _patch_workflow,
    _second_pass_template,
    step03c_second_pass,
)


def _value(content: str, key: str) -> str | None:
    """Read a `key=value` line out of a workflow file's text."""
    m = re.search(rf"^{re.escape(key)}=(.*)$", content, re.MULTILINE)
    return m.group(1) if m else None


# The calibrated values FragPipe bakes into fragpipe-second-pass.workflow, and
# which the reference's own second.workflow carries verbatim (D-051).
_CALIBRATED = {
    "msfragger.calibrate_mass": "0",
    "msfragger.fragment_mass_tolerance": "10.0",
    "msfragger.fragment_mass_units": "1",
    "msfragger.use_topN_peaks": "300",
    "msfragger.minimum_ratio": "0.0",
    "msfragger.intensity_transform": "1",
    "msfragger.remove_precursor_peak": "0",
}


def _fake_generated_workflow(step3a_dir: Path) -> Path:
    """Write a stand-in for FragPipe's auto-generated second-pass workflow."""
    step3a_dir.mkdir(parents=True, exist_ok=True)
    wf = step3a_dir / GENERATED_SECOND_PASS_WORKFLOW
    lines = [f"{k}={v}" for k, v in _CALIBRATED.items()] + [
        "database.db-path=/tools/databases",
        "database.decoy-tag=",
        "ionquant.minisotopes=2",
        "ionquant.minscans=3",
        "msfragger.clip_nTerm_M=true",
        "msfragger.misc.fragger.enzyme-dropdown-1=stricttrypsin",
        "msfragger.search_enzyme_cut_1=KR",
        "msfragger.search_enzyme_name_1=stricttrypsin",
        "msfragger.search_enzyme_nocut_1=",
        "msbooster.find-best-rt-model=false",
        "msbooster.run-msbooster=true",
        "msbooster.predict-rt=true",
        "msbooster.predict-spectra=true",
    ]
    wf.write_text("\n".join(lines) + "\n")
    return wf


class TestSecondPassTemplate:
    """Step 3c bases its search on FragPipe's own second-pass workflow (D-051).

    FragPipe writes `fragpipe-second-pass.workflow` during the first pass with
    the calibration already applied (`calibrate_mass=0` plus the optimized
    tolerance/topN/transform values). The reference pipeline seds *that* file —
    not the pristine `generic.workflow` — so reusing it both skips ~5-6 min of
    redundant calibration and matches the reference's search parameters exactly.
    """

    def test_prefers_fragpipe_generated_workflow(self, tmp_path: Path) -> None:
        step3a = tmp_path / "03a_first_pass"
        generated = _fake_generated_workflow(step3a)
        template, calibrated = _second_pass_template(step3a)
        assert template == generated
        assert calibrated is True

    def test_falls_back_to_bundled_template(self, tmp_path: Path) -> None:
        step3a = tmp_path / "03a_first_pass"
        step3a.mkdir()
        template, calibrated = _second_pass_template(step3a)
        assert template == WORKFLOW_TEMPLATE
        assert calibrated is False


class TestPatchWorkflow:
    def test_inherits_calibration_from_generated_workflow(self, tmp_path: Path) -> None:
        """The calibrated values must survive patching untouched."""
        generated = _fake_generated_workflow(tmp_path / "03a_first_pass")
        out = _patch_workflow(generated.read_text(), Path("/db/decoy.fasta"))
        for key, expected in _CALIBRATED.items():
            assert _value(out, key) == expected, key

    def test_applies_nocleavage_patches(self, tmp_path: Path) -> None:
        generated = _fake_generated_workflow(tmp_path / "03a_first_pass")
        out = _patch_workflow(generated.read_text(), Path("/db/decoy.fasta"))
        assert _value(out, "database.db-path") == "/db/decoy.fasta"
        assert _value(out, "database.decoy-tag") == "rev_"
        assert _value(out, "ionquant.minisotopes") == "1"
        assert _value(out, "ionquant.minscans") == "1"
        assert _value(out, "msfragger.clip_nTerm_M") == "false"
        assert _value(out, "msfragger.misc.fragger.enzyme-dropdown-1") == "nocleavage"
        assert _value(out, "msfragger.search_enzyme_cut_1") == "@"
        assert _value(out, "msfragger.search_enzyme_name_1") == "nocleavage"
        assert _value(out, "msfragger.search_enzyme_nocut_1") == "@"
        # `find-best-rt-model` stays pinned false (the reference sets it false);
        # it picks the RT model and does not gate MSBooster itself.
        assert _value(out, "msbooster.find-best-rt-model") == "false"

    def test_leaves_msbooster_running(self, tmp_path: Path) -> None:
        """MSBooster must survive the patch chain — it produces the score columns.

        FragPipe writes `SpectralSim`/`RTScore` into the second-pass psm.tsv only
        when MSBooster runs, and Step 7 carries psm.tsv columns through verbatim.
        Disabling it (as cfd4886 did, to skip redundant calibration PNGs) left
        both columns null in every rerun (D-069). The reference workflows ship
        these as true, so the patch chain must not touch them.
        """
        generated = _fake_generated_workflow(tmp_path / "03a_first_pass")
        out = _patch_workflow(generated.read_text(), Path("/db/decoy.fasta"))
        assert _value(out, "msbooster.run-msbooster") == "true"
        assert _value(out, "msbooster.predict-rt") == "true"
        assert _value(out, "msbooster.predict-spectra") == "true"

    def test_forces_remove_precursor_peak_off_unconditionally(self) -> None:
        """The reference mandates remove_precursor_peak=0 for the second pass.

        It must never be left to whatever the template happens to carry — a
        template with `=1` would silently change the science.
        """
        out = _patch_workflow(
            "msfragger.remove_precursor_peak=1\n", Path("/db/decoy.fasta"),
        )
        assert _value(out, "msfragger.remove_precursor_peak") == "0"

    def test_bundled_template_fallback_still_calibrates(self) -> None:
        """Without FragPipe's workflow we must fall back to self-calibration.

        `generic.workflow` carries `calibrate_mass=2`, so Step 3c runs its own
        calibration — slower, and it diverges from the reference, but it is
        correct and must not silently produce an uncalibrated search.
        """
        out = _patch_workflow(WORKFLOW_TEMPLATE.read_text(), Path("/db/decoy.fasta"))
        assert _value(out, "msfragger.calibrate_mass") == "2"
        assert _value(out, "msfragger.remove_precursor_peak") == "0"


def _make_env(tmp_path: Path) -> ToolEnvironment:
    (tmp_path / "fragpipe-24.0" / "bin").mkdir(parents=True)
    (tmp_path / "fragpipe-24.0" / "bin" / "fragpipe").touch()
    phil_dir = tmp_path / "fragpipe-24.0" / "tools" / "Philosopher"
    phil_dir.mkdir(parents=True)
    (phil_dir / "philosopher-v5.1.3-RC9").touch()
    return ToolEnvironment(tools_dir=tmp_path)


class TestInputValidation:
    def test_missing_mzml_dir(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        with pytest.raises(FileNotFoundError, match="mzML directory not found"):
            step03c_second_pass(tmp_path / "no_mzml", tmp_path / "candidates.fa", tmp_path, env)

    def test_empty_mzml_dir(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        fasta = tmp_path / "candidates.fa"
        fasta.touch()
        with pytest.raises(FileNotFoundError, match="No .mzML files found"):
            step03c_second_pass(mzml_dir, fasta, tmp_path, env)

    def test_missing_pep_candidates(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        with pytest.raises(FileNotFoundError, match="Variant FASTA not found"):
            step03c_second_pass(mzml_dir, tmp_path / "nonexistent.fa", tmp_path, env)

    def test_missing_philosopher(self, tmp_path: Path) -> None:
        (tmp_path / "fragpipe-24.0" / "bin").mkdir(parents=True)
        (tmp_path / "fragpipe-24.0" / "bin" / "fragpipe").touch()
        env = ToolEnvironment(tools_dir=tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        fasta = tmp_path / "candidates.fa"
        fasta.touch()
        with pytest.raises(FileNotFoundError, match="Philosopher not found"):
            step03c_second_pass(mzml_dir, fasta, tmp_path, env)

    def test_missing_fragpipe(self, tmp_path: Path) -> None:
        phil_dir = tmp_path / "fragpipe-24.0" / "tools" / "Philosopher"
        phil_dir.mkdir(parents=True)
        (phil_dir / "philosopher-v5.1.3-RC9").touch()
        env = ToolEnvironment(tools_dir=tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        fasta = tmp_path / "candidates.fa"
        fasta.touch()
        with pytest.raises(FileNotFoundError, match="FragPipe not found"):
            step03c_second_pass(mzml_dir, fasta, tmp_path, env)


class TestBundledTemplateHasEveryPatchedKey:
    """A patch whose key is absent from the template silently does nothing.

    `re.sub` is a no-op when the pattern misses, so a renamed or missing key
    would leave the second pass running with FragPipe's defaults — no error,
    wrong science. Pin every key we rely on.
    """

    @pytest.mark.parametrize("key", [
        "database.db-path",
        "database.decoy-tag",
        "ionquant.minisotopes",
        "ionquant.minscans",
        "msfragger.calibrate_mass",
        "msfragger.clip_nTerm_M",
        "msfragger.misc.fragger.enzyme-dropdown-1",
        "msfragger.remove_precursor_peak",
        "msfragger.search_enzyme_cut_1",
        "msfragger.search_enzyme_name_1",
        "msfragger.search_enzyme_nocut_1",
        "msbooster.find-best-rt-model",
        "msbooster.run-msbooster",
        "msbooster.predict-rt",
        "msbooster.predict-spectra",
    ])
    def test_key_present_in_bundled_workflow(self, key: str) -> None:
        assert _value(WORKFLOW_TEMPLATE.read_text(), key) is not None
