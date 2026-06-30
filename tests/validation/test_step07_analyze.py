"""Step 7 validation: SAV filtering against mock data pipeline output."""

import pytest
from pathlib import Path
from src.tarsus.steps.step07_analyze_outputs import analyze_outputs
from .conftest import load_expected, capture_expected


@pytest.mark.lsf
def test_step07_analyze(mock_data, tool_env, tmp_path):
    """Run Step 7 against mock pipeline outputs from Steps 2-6."""
    # This test needs the outputs from Steps 2-6. 
    # For first run: set up a mini pipeline run in tmp_path.
    # On subsequent runs: compare against golden file.
    
    # TODO: Wire this after Steps 2-6 are validated.
    # For now, skip with a message.
    pytest.skip("Requires Steps 2-6 outputs — wire after those pass")
