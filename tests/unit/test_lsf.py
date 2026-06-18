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
