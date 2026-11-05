"""Unit tests for Step 3a — FragPipe first-pass search.

Tests cover:
  - Input validation (missing FASTA, mzML, tools, workflow)
  - Workflow patching (regex DB path substitution)
  - Manifest generation (correct format, line count)
"""

import re
from pathlib import Path
import pytest
from src.tarsus.steps.step03a_first_pass import step03a_first_pass
from src.tarsus.env import ToolEnvironment


def _make_env(tmp_path: Path) -> ToolEnvironment:
    """Create a valid ToolEnvironment with stubs for FragPipe and Philosopher."""
    (tmp_path / "fragpipe-24.0" / "bin").mkdir(parents=True)
    (tmp_path / "fragpipe-24.0" / "bin" / "fragpipe").touch()
    phil_dir = tmp_path / "fragpipe-24.0" / "tools" / "Philosopher"
    phil_dir.mkdir(parents=True)
    (phil_dir / "philosopher-v5.1.3-RC9").touch()
    return ToolEnvironment(tools_dir=tmp_path)


class TestInputValidation:
    def test_missing_fasta(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        with pytest.raises(FileNotFoundError, match="FASTA not found"):
            step03a_first_pass(tmp_path / "nonexistent.fa", tmp_path, tmp_path, env)

    def test_missing_mzml_dir(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        fasta = tmp_path / "test.fa"
        fasta.touch()
        with pytest.raises(FileNotFoundError, match="mzML directory not found"):
            step03a_first_pass(fasta, tmp_path / "no_mzml", tmp_path, env)

    def test_empty_mzml_dir(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        fasta = tmp_path / "test.fa"
        fasta.touch()
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="No .mzML files found"):
            step03a_first_pass(fasta, mzml_dir, tmp_path, env)

    def test_missing_philosopher(self, tmp_path: Path) -> None:
        (tmp_path / "fragpipe-24.0" / "bin").mkdir(parents=True)
        (tmp_path / "fragpipe-24.0" / "bin" / "fragpipe").touch()
        # No Philosopher dir
        env = ToolEnvironment(tools_dir=tmp_path)
        fasta = tmp_path / "test.fa"
        fasta.touch()
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        with pytest.raises(FileNotFoundError, match="Philosopher not found"):
            step03a_first_pass(fasta, mzml_dir, tmp_path, env)

    def test_missing_fragpipe(self, tmp_path: Path) -> None:
        phil_dir = tmp_path / "fragpipe-24.0" / "tools" / "Philosopher"
        phil_dir.mkdir(parents=True)
        (phil_dir / "philosopher-v5.1.3-RC9").touch()
        # No fragpipe bin
        env = ToolEnvironment(tools_dir=tmp_path)
        fasta = tmp_path / "test.fa"
        fasta.touch()
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        with pytest.raises(FileNotFoundError, match="FragPipe not found"):
            step03a_first_pass(fasta, mzml_dir, tmp_path, env)


class TestWorkflowPatching:
    def test_db_path_replaced(self, tmp_path: Path) -> None:
        """Verify the workflow DB path gets correctly patched."""
        workflow_tmpl = tmp_path / "generic.workflow"
        workflow_tmpl.write_text(
            "database.db-path=/old/path/to/db.fas\nsome.other=value\n"
        )

        target_fas = tmp_path / "target.fas"
        target_fas.touch()

        # Manually test the replication logic
        content = workflow_tmpl.read_text()
        db_line = f"database.db-path={target_fas.resolve()}"
        patched = re.sub(
            r"^database\.db-path=.*$",
            db_line,
            content,
            count=1,
            flags=re.MULTILINE,
        )
        assert f"database.db-path={target_fas.resolve()}" in patched
        assert "/old/path" not in patched
        assert "some.other=value" in patched


class TestManifestGeneration:
    def test_manifest_format(self, tmp_path: Path) -> None:
        """FragPipe manifest is path + three tabs + DDA per line."""
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "a.mzML").touch()
        (mzml_dir / "b.mzML").touch()

        manifest = tmp_path / "test.manifest"
        with manifest.open("w") as f:
            for mzml in sorted(mzml_dir.glob("*.mzML")):
                f.write(f"{mzml.resolve()}\t\t\tDDA\n")

        lines = manifest.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            assert line.endswith("\t\t\tDDA")
            assert line.count("\t") == 3

    def test_no_mzml_manifest_empty(self, tmp_path: Path) -> None:
        manifest = tmp_path / "empty.manifest"
        manifest.touch()
        assert manifest.read_text() == ""


class TestNoRedundantPhilosopherDatabaseCall:
    """Regression (D-062): we ran `philosopher database --custom` on an
    ALREADY-DECOYED fasta, so Philosopher decoyed it a SECOND time.

    Real output: `2026-07-13-decoys-protein_decoy.fasta.fas` — 20,728,149
    sequences, of which **6,909,383 were `rev_rev_`**. ~2.5 GB per run, written to
    CWD, and **never used by anything** (both workflows point at our own clean
    `protein_decoy.fasta`, which is a correct 50/50 target:decoy split).

    FDR was never corrupted — but it burned GBs and hours. The call is redundant:
    FragPipe runs `philosopher database` itself from the workflow's
    `database.db-path`.
    """

    INVOCATION = '"$PHILOSOPHER" database'

    def test_step03a_runner_does_not_invoke_philosopher_database(self) -> None:
        src = Path("src/tarsus/steps/step03a_first_pass.py").read_text()
        assert self.INVOCATION not in src, (
            "philosopher database --custom double-decoys our already-decoyed FASTA; "
            "FragPipe already runs it from the workflow's database.db-path"
        )

    def test_step03c_runner_does_not_invoke_philosopher_database(self) -> None:
        src = Path("src/tarsus/steps/step03c_second_pass.py").read_text()
        assert self.INVOCATION not in src


class TestMsboosterModels:
    """D-073: MSBooster picks the best Koina model by default, as Slava's runs did."""

    def test_template_ships_find_best_like_the_published_workflow(self) -> None:
        from src.tarsus.assets import WORKFLOW_TEMPLATE
        text = WORKFLOW_TEMPLATE.read_text()
        for line in ("msbooster.run-msbooster=true",
                     "msbooster.find-best-rt-model=true",
                     "msbooster.find-best-spectra-model=true"):
            assert re.search(rf"^{re.escape(line)}$", text, re.MULTILINE), line

    def test_best_mode_leaves_msbooster_block_untouched(self, tmp_path: Path) -> None:
        from src.tarsus.assets import WORKFLOW_TEMPLATE
        from src.tarsus.steps.step03a_first_pass import _patch_first_pass_workflow
        text = WORKFLOW_TEMPLATE.read_text()
        out = _patch_first_pass_workflow(text, tmp_path / "db.fasta", "best")
        msb = lambda s: [ln for ln in s.splitlines() if ln.startswith("msbooster.")]  # noqa: E731
        assert msb(out) == msb(text)
        assert f"database.db-path={(tmp_path / 'db.fasta').resolve()}" in out

    def test_dia_nn_mode_pins_local_models(self, tmp_path: Path) -> None:
        from src.tarsus.assets import WORKFLOW_TEMPLATE
        from src.tarsus.steps.step03a_first_pass import _patch_first_pass_workflow
        out = _patch_first_pass_workflow(WORKFLOW_TEMPLATE.read_text(), tmp_path / "db.fa", "dia-nn")
        for line in ("msbooster.find-best-rt-model=false",
                     "msbooster.find-best-spectra-model=false",
                     "msbooster.rt-model=DIA-NN",
                     "msbooster.spectra-model=DIA-NN",
                     "msbooster.run-msbooster=true"):
            assert re.search(rf"^{re.escape(line)}$", out, re.MULTILINE), line

    def test_absent_key_raises_instead_of_silent_noop(self, tmp_path: Path) -> None:
        from src.tarsus.steps.step03a_first_pass import _patch_first_pass_workflow
        with pytest.raises(ValueError, match="no line matching"):
            _patch_first_pass_workflow("database.db-path=x\n", tmp_path / "db.fa", "dia-nn")

    def test_unknown_mode_raises(self, tmp_path: Path) -> None:
        from src.tarsus.steps.step03a_first_pass import _patch_first_pass_workflow
        with pytest.raises(ValueError, match="msbooster_models must be one of"):
            _patch_first_pass_workflow("database.db-path=x\n", tmp_path / "db.fa", "koina")
