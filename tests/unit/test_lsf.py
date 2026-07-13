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
from pathlib import Path
from src.tarsus.lsf import wait_for_jobs, job_log_verdict


class TestWaitForJobsPurgedJob:
    """A purged job is NOT a failure.

    LSF drops completed jobs from `bjobs` after ~1h, so on a 75-minute Step 5 the
    earliest jobs vanish precisely *because* they finished. wait_for_jobs must
    return them as unconfirmed for the caller to settle against the artifact —
    never stall on them, and never raise.

    Note stdout is now `"<jobid> <stat>"`: statuses are fetched for all jobs in
    ONE `bjobs` call, not one call per job.
    """

    @patch("src.tarsus.lsf.subprocess.run")
    def test_purged_job_not_found_on_stderr(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            stdout="", stderr="Job <12345> is not found", returncode=255,
        )
        unconfirmed = wait_for_jobs([12345], poll_seconds=0)  # must not hang or raise
        assert unconfirmed == [12345]

    @patch("src.tarsus.lsf.subprocess.run")
    def test_purged_job_empty_stdout_no_stderr(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        assert wait_for_jobs([12345], poll_seconds=0) == [12345]

    @patch("src.tarsus.lsf.subprocess.run")
    def test_running_job_waits_then_done_exits(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            MagicMock(stdout="12345 RUN", stderr="", returncode=0),
            MagicMock(stdout="12345 DONE", stderr="", returncode=0),
        ]
        assert wait_for_jobs([12345], poll_seconds=0) == []

    @patch("src.tarsus.lsf.subprocess.run")
    def test_exit_job_raises(self, mock_run: MagicMock) -> None:
        """EXIT is a definite failure — unlike a purge — and must be loud."""
        mock_run.return_value = MagicMock(stdout="12345 EXIT", stderr="", returncode=0)
        with pytest.raises(RuntimeError, match="LSF job\\(s\\) failed"):
            wait_for_jobs([12345], poll_seconds=0)

    @patch("src.tarsus.lsf.subprocess.run")
    def test_pend_job_then_purged_exits(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            MagicMock(stdout="12345 PEND", stderr="", returncode=0),
            MagicMock(stdout="", stderr="Job <12345> is not found", returncode=255),
        ]
        assert wait_for_jobs([12345], poll_seconds=0) == [12345]


class TestWaitForJobsDoesNotTrustLsfStatus:
    """LSF status is not a reliable completion signal — the artifact is.

    Three real defects, found while investigating a "job 689403 exited" crash
    that could not be diagnosed because nothing recorded which chunk that job
    was:

    1. `bjobs` returncode was never checked. We spawn one `bjobs` per job per
       30s poll — 4,784 of them on a big Step 5 — which hammers the LSF daemon.
       A transient failure returns empty stdout, and the old code read "empty"
       as "gone, therefore fine". **A job that died was silently recorded as
       successful.**
    2. A purged job ("not found") was likewise assumed successful. Purge means
       state *unknown*, not success.
    3. It raised on the FIRST EXIT, discarding the work of thousands of jobs
       that were still running.
    """

    @patch("src.tarsus.lsf.subprocess.run")
    def test_transient_bjobs_failure_is_retried_not_assumed_done(
        self, mock_run: MagicMock,
    ) -> None:
        """A failed `bjobs` call must NOT be read as 'job finished'."""
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="batch system daemon not responding",
                      returncode=1),                       # transient failure
            MagicMock(stdout="12345 RUN", stderr="", returncode=0),
            MagicMock(stdout="12345 DONE", stderr="", returncode=0),
        ]
        failed = wait_for_jobs([12345], poll_seconds=0)
        assert failed == []
        assert mock_run.call_count == 3, "must retry, not give up on the first error"

    @patch("src.tarsus.lsf.subprocess.run")
    def test_exit_does_not_fail_fast_and_is_returned(self, mock_run: MagicMock) -> None:
        """One EXIT must not abort the wait — report it, let the caller judge."""
        mock_run.return_value = MagicMock(
            stdout="1 EXIT\n2 DONE\n3 EXIT", stderr="", returncode=0,
        )
        failed = wait_for_jobs([1, 2, 3], poll_seconds=0, raise_on_failure=False)
        assert sorted(failed) == [1, 3]

    @patch("src.tarsus.lsf.subprocess.run")
    def test_raises_naming_every_failure_not_just_the_first(
        self, mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(
            stdout="1 EXIT\n2 DONE\n3 EXIT", stderr="", returncode=0,
        )
        with pytest.raises(RuntimeError) as exc:
            wait_for_jobs([1, 2, 3], poll_seconds=0,
                          job_labels={1: "chunk_0000", 3: "chunk_0042"})
        msg = str(exc.value)
        assert "chunk_0000" in msg and "chunk_0042" in msg, "must name the chunks"

    @patch("src.tarsus.lsf.subprocess.run")
    def test_purged_job_is_reported_unknown_not_successful(
        self, mock_run: MagicMock,
    ) -> None:
        """A purged job's outcome is unknowable from LSF — say so."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Job <12345> is not found", returncode=255,
        )
        failed = wait_for_jobs([12345], poll_seconds=0, raise_on_failure=False)
        assert failed == [12345], "purge is state-unknown; the caller must check the artifact"

    @patch("src.tarsus.lsf.subprocess.run")
    def test_queries_all_jobs_in_one_bjobs_call(self, mock_run: MagicMock) -> None:
        """One `bjobs` per poll, not one per job — the polling storm is the bug."""
        mock_run.return_value = MagicMock(
            stdout="1 DONE\n2 DONE\n3 DONE", stderr="", returncode=0,
        )
        wait_for_jobs([1, 2, 3], poll_seconds=0)
        assert mock_run.call_count == 1
        argv = mock_run.call_args[0][0]
        for jid in ("1", "2", "3"):
            assert jid in argv


class TestLogIsGroundTruthNotBjobs:
    """The reported scenario: `bjobs` said EXIT, the job's own log said success.

    LSF purges completed jobs from `bjobs` after ~1h, so on a long fan-out the
    live status is unreliable — but LSF's epilogue in each job's -oo log
    (`Successfully completed.` / `Exited with exit code N`) is durable and
    per-job. Trust the log.
    """

    def test_job_log_verdict_success(self, tmp_path: Path) -> None:
        log = tmp_path / "chunk_0000.tsv.log"
        log.write_text("...PepQuery output...\n\nSuccessfully completed.\n")
        assert job_log_verdict(log) == "success"

    def test_job_log_verdict_failure(self, tmp_path: Path) -> None:
        log = tmp_path / "chunk_0001.tsv.log"
        log.write_text("TERM_MEMLIMIT: job killed after reaching LSF memory limit.\n")
        assert job_log_verdict(log) == "failure"

    def test_job_log_verdict_unknown_when_no_epilogue(self, tmp_path: Path) -> None:
        log = tmp_path / "chunk_0002.tsv.log"
        log.write_text("still running...\n")
        assert job_log_verdict(log) is None

    def test_job_log_verdict_missing_log(self, tmp_path: Path) -> None:
        assert job_log_verdict(tmp_path / "nope.log") is None

    @patch("src.tarsus.lsf.subprocess.run")
    def test_exit_status_overridden_by_successful_log(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """THE BUG: bjobs reported EXIT and the master died — but the job succeeded."""
        log = tmp_path / "chunk_0000.tsv.log"
        log.write_text("Matched spectra: 8\n\nSuccessfully completed.\n")
        mock_run.return_value = MagicMock(stdout="689403 EXIT", stderr="", returncode=0)

        failed = wait_for_jobs(
            [689403], poll_seconds=0,
            job_labels={689403: "chunk_0000"},
            job_logs={689403: log},
        )
        assert failed == [], "a job whose own log says it completed must not be a failure"

    @patch("src.tarsus.lsf.subprocess.run")
    def test_purged_job_with_successful_log_is_success(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """Purged from bjobs BECAUSE it finished — the log proves it."""
        log = tmp_path / "chunk_0007.tsv.log"
        log.write_text("Successfully completed.\n")
        mock_run.return_value = MagicMock(
            stdout="", stderr="Job <1> is not found", returncode=255,
        )
        assert wait_for_jobs([1], poll_seconds=0, job_logs={1: log}) == []

    @patch("src.tarsus.lsf.subprocess.run")
    def test_purged_job_with_failed_log_is_a_failure(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """The converse: purge must not launder a real failure into success."""
        log = tmp_path / "chunk_0008.tsv.log"
        log.write_text("Exited with exit code 255.\n")
        mock_run.return_value = MagicMock(
            stdout="", stderr="Job <2> is not found", returncode=255,
        )
        with pytest.raises(RuntimeError, match="chunk_0008"):
            wait_for_jobs([2], poll_seconds=0,
                          job_labels={2: "chunk_0008"}, job_logs={2: log})

    @patch("src.tarsus.lsf.subprocess.run")
    def test_failure_message_names_chunk_and_log(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """A failure must be diagnosable: which chunk, which log.

        The crash that prompted this read "LSF job 689403 exited with failure" —
        and nothing anywhere recorded which chunk 689403 was, so the claim could
        not be checked.
        """
        log = tmp_path / "chunk_0042.tsv.log"
        log.write_text("Exited with exit code 1.\n")
        mock_run.return_value = MagicMock(stdout="99 EXIT", stderr="", returncode=0)
        with pytest.raises(RuntimeError) as exc:
            wait_for_jobs([99], poll_seconds=0,
                          job_labels={99: "chunk_0042"}, job_logs={99: log})
        msg = str(exc.value)
        assert "chunk_0042" in msg and str(log) in msg
