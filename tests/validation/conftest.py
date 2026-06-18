"""Validation framework — shared fixtures and expected-output helpers."""

import yaml
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest

from src.tarsus.env import ToolEnvironment


# ── Trial data paths ────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
TOOLS_DIR = PROJECT_ROOT / "tools"
EXPECTED_DIR = Path(__file__).parent / "expected"


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def trial_data() -> dict:
    """Paths to all trial data files."""
    return {
        "fasta": DATA_DIR / "protein.fasta",
        "raw_files": sorted(DATA_DIR.glob("*.raw")),
        "mzml_dir": OUTPUT_DIR / "01_mzml",
        "base_name_ls": "HouYM-25-G140-AstralDDA-AlaGGC-LS-1",
        "base_name_hs": "HouYM-25-G140-AstralDDA-AlaGGC-HS-1",
    }


@pytest.fixture(scope="session")
def tool_env() -> ToolEnvironment:
    return ToolEnvironment.from_env()


# ── Expected output helpers ──────────────────────────────────────────────


def load_expected(step: str) -> dict | None:
    """Load expected output schema for *step*, or None if not yet captured."""
    path = EXPECTED_DIR / f"{step}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def capture_expected(step: str, data: dict) -> None:
    """Write *data* as the expected output schema for *step*."""
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPECTED_DIR / f"{step}.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"\n[INFO] Captured expected output to {path}")


# ── mzML validation ─────────────────────────────────────────────────────


def validate_mzml(path: Path) -> tuple[bool, dict]:
    """Check an mzML file is valid XML and extract basic stats.

    Returns (is_valid, stats_dict).
    """
    if not path.exists():
        return False, {"error": "file not found"}
    stats: dict = {"size_mb": round(path.stat().st_size / 1_048_576, 1)}

    try:
        tree = ET.parse(path)
        root = tree.getroot()
        ns = {"mzml": "http://psi.hupo.org/ms/mzml"}
        # Count scans (spectrum elements)
        scans = root.findall(".//mzml:spectrum", ns)
        stats["scan_count"] = len(scans)
        return True, stats
    except ET.ParseError as e:
        stats["error"] = str(e)
        return False, stats
