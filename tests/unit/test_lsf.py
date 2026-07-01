"""Unit tests for LSF helpers — no bsub/bjobs required."""

import pytest
from src.tarsus.lsf import _parse_job_id


class TestParseJobId:
    def test_standard_output(self) -> None:
        output = "Job <12345> is submitted to queue <gsla-cpu>."
        assert _parse_job_id(output) == 12345

    def test_different_format(self) -> None:
        output = "Job <999999> is submitted to default queue."
        assert _parse_job_id(output) == 999999

    def test_large_job_id(self) -> None:
        output = "Job <2147483647> is submitted."
        assert _parse_job_id(output) == 2147483647

    def test_no_job_id(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse job ID"):
            _parse_job_id("No job here")

    def test_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse job ID"):
            _parse_job_id("")

    def test_non_numeric_angle_brackets(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse job ID"):
            _parse_job_id("Job <abc> is submitted.")

    def test_not_angle_brackets(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse job ID"):
            _parse_job_id("Job [12345] is submitted.")

    def test_multiple_numbers(self) -> None:
        output = "Job <54321> is submitted to queue <testq>."
        assert _parse_job_id(output) == 54321

    def test_multiple_angle_brackets_first_wins(self) -> None:
        output = "Job <42> is submitted to queue <99>."
        assert _parse_job_id(output) == 42


from unittest.mock import patch, MagicMock
from src.tarsus.lsf import wait_for_jobs


class TestWaitForJobsPurgedJob:
    """wait_for_jobs must not stall on purged/deleted job IDs."""

    @patch("src.tarsus.lsf.subprocess.run")
    def test_purged_job_not_found_on_stderr(self, mock_run: MagicMock) -> None:
        """bjobs returns empty stdout + 'not found' on stderr for purged job."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Job <12345> is not found", returncode=0
        )
        wait_for_jobs([12345])  # Must return without hanging

    @patch("src.tarsus.lsf.subprocess.run")
    def test_purged_job_empty_stdout_no_stderr(self, mock_run: MagicMock) -> None:
        """Defensive: empty stdout even without 'not found' on stderr."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="", returncode=0
        )
        wait_for_jobs([12345])  # Must return without hanging

    @patch("src.tarsus.lsf.subprocess.run")
    def test_running_job_waits_then_done_exits(self, mock_run: MagicMock) -> None:
        """A RUN status keeps the loop going, then DONE exits."""
        mock_run.side_effect = [
            MagicMock(stdout="RUN", stderr="", returncode=0),
            MagicMock(stdout="DONE", stderr="", returncode=0),
        ]
        wait_for_jobs([12345])

    @patch("src.tarsus.lsf.subprocess.run")
    def test_exit_job_is_terminal(self, mock_run: MagicMock) -> None:
        """EXIT status is terminal (job failed but is done)."""
        mock_run.return_value = MagicMock(
            stdout="EXIT", stderr="", returncode=0
        )
        wait_for_jobs([12345])  # EXIT is not in active list → exits immediately

    @patch("src.tarsus.lsf.subprocess.run")
    def test_pend_job_then_purged_exits(self, mock_run: MagicMock) -> None:
        """PEND (active), then purged ('not found') — exits cleanly."""
        mock_run.side_effect = [
            MagicMock(stdout="PEND", stderr="", returncode=0),
            MagicMock(stdout="", stderr="Job <99999> is not found", returncode=0),
        ]
        wait_for_jobs([99999])
