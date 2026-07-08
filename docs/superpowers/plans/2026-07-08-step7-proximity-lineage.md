# Step 7 Proximity-Based Lineage Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unblock Step 7 (currently produces `subs.ipc` with 0 rows) by accepting PepQuery/PDV evidence that is *proximate* (same file+charge, RT/mass within tolerance) to a Step 3c candidate's own spectrum, in addition to requiring an exact title match — without touching Steps 1–6 or rerunning any LSF jobs.

**Architecture:** A new small module builds a one-time `spectrum_title -> (file, charge, rt, mass)` lookup by scanning the existing PepQuery index MGF files, cached to a parquet file. `step07_analyze_outputs.py` gains pure proximity-matching helper functions and threads a new optional `index_dir` parameter through `analyze_outputs()`, replacing its two exact-title membership checks with "exact, or proximate" checks, and adds a `match_type` column to the output.

**Tech Stack:** Python 3.11, polars, pytest (existing project stack — no new dependencies).

## Global Constraints

- File name and charge must match exactly between a Step 3c candidate spectrum and any PepQuery/PDV evidence spectrum considered as a match for it (from spec: `docs/superpowers/specs/2026-07-08-step7-proximity-lineage-design.md`).
- Retention time tolerance: `24.0` seconds.
- Precursor mass tolerance: `20.0` ppm.
- No changes to Steps 1–6, their outputs, or their sentinels.
- `analyze_outputs()`'s existing exact-match behavior must remain fully intact when `index_dir` is not supplied (backward compatibility for the existing fixture-based test).
- All new code follows existing project conventions: type annotations on every function, docstrings, Polars for tabular data, pytest for testing (no LSF/real tool calls in unit tests).

---

### Task 1: RT/mass cache builder module

**Files:**
- Create: `src/tarsus/steps/_index_rt_cache.py`
- Test: `tests/unit/test_index_rt_cache.py`

**Interfaces:**
- Produces: `build_rt_mass_cache(index_dir: Path) -> pl.DataFrame` — columns `spectrum_title` (str), `file_name` (str), `charge` (int), `rt_seconds` (float), `mass` (float, neutral monoisotopic mass).
- Produces: `load_or_build_rt_mass_cache(index_dir: Path) -> pl.DataFrame` — same schema; reads/writes `<index_dir>/_rt_mass_cache.parquet`.
- Produces: `CACHE_FILENAME: str = "_rt_mass_cache.parquet"` (module constant, used by Task 3's tests to locate the cache file).

- [ ] **Step 1: Write the failing test for `build_rt_mass_cache`**

Create `tests/unit/test_index_rt_cache.py`:

```python
"""Unit tests for the PepQuery index RT/mass cache builder."""

from pathlib import Path
import polars as pl
from src.tarsus.steps._index_rt_cache import (
    build_rt_mass_cache,
    load_or_build_rt_mass_cache,
    CACHE_FILENAME,
)


def _write_mgf(path: Path, entries: list[dict]) -> None:
    """Write a minimal synthetic MGF file with the given spectrum entries."""
    lines: list[str] = []
    for e in entries:
        lines.append("BEGIN IONS")
        lines.append(f"TITLE={e['title']}")
        lines.append(f"PEPMASS={e['mz']}")
        lines.append(f"RTINSECONDS={e['rt']}")
        lines.append(f"CHARGE={e['charge']}+")
        lines.append("100.0 1000.0")
        lines.append("END IONS")
    path.write_text("\n".join(lines) + "\n")


class TestBuildRtMassCache:
    def test_single_file_single_spectrum(self, tmp_path: Path) -> None:
        index_dir = tmp_path / "pepquery_index"
        index_dir.mkdir()
        _write_mgf(
            index_dir / "100.mgf",
            [{"title": "dev_sub:1:2", "mz": 468.21698, "rt": 165.680841, "charge": 2}],
        )
        df = build_rt_mass_cache(index_dir)
        assert len(df) == 1
        assert df["spectrum_title"][0] == "dev_sub:1:2"
        assert df["file_name"][0] == "dev_sub"
        assert df["charge"][0] == 2
        assert df["rt_seconds"][0] == 165.680841
        # neutral mass = mz*z - z*proton = 468.21698*2 - 2*1.007276466
        assert abs(df["mass"][0] - 934.4194141) < 1e-3

    def test_multiple_spectra_same_file(self, tmp_path: Path) -> None:
        index_dir = tmp_path / "pepquery_index"
        index_dir.mkdir()
        _write_mgf(
            index_dir / "100.mgf",
            [
                {"title": "dev_sub:1:2", "mz": 400.0, "rt": 10.0, "charge": 2},
                {"title": "dev_sub:2:3", "mz": 500.0, "rt": 20.0, "charge": 3},
            ],
        )
        df = build_rt_mass_cache(index_dir)
        assert len(df) == 2
        assert set(df["spectrum_title"].to_list()) == {"dev_sub:1:2", "dev_sub:2:3"}

    def test_multiple_files(self, tmp_path: Path) -> None:
        index_dir = tmp_path / "pepquery_index"
        index_dir.mkdir()
        _write_mgf(index_dir / "100.mgf", [{"title": "a:1:2", "mz": 400.0, "rt": 1.0, "charge": 2}])
        _write_mgf(index_dir / "200.mgf", [{"title": "b:1:2", "mz": 400.0, "rt": 1.0, "charge": 2}])
        df = build_rt_mass_cache(index_dir)
        assert len(df) == 2

    def test_incomplete_entry_skipped(self, tmp_path: Path) -> None:
        """An entry missing a required field (no CHARGE) is silently skipped."""
        index_dir = tmp_path / "pepquery_index"
        index_dir.mkdir()
        (index_dir / "100.mgf").write_text(
            "BEGIN IONS\nTITLE=broken:1:2\nPEPMASS=400.0\nRTINSECONDS=1.0\nEND IONS\n",
        )
        df = build_rt_mass_cache(index_dir)
        assert len(df) == 0

    def test_malformed_title_skipped(self, tmp_path: Path) -> None:
        """A title that doesn't split into exactly 3 ':'-separated parts is skipped."""
        index_dir = tmp_path / "pepquery_index"
        index_dir.mkdir()
        _write_mgf(
            index_dir / "100.mgf",
            [{"title": "no_colons_here", "mz": 400.0, "rt": 1.0, "charge": 2}],
        )
        df = build_rt_mass_cache(index_dir)
        assert len(df) == 0


class TestLoadOrBuildRtMassCache:
    def test_builds_and_writes_cache(self, tmp_path: Path) -> None:
        index_dir = tmp_path / "pepquery_index"
        index_dir.mkdir()
        _write_mgf(
            index_dir / "100.mgf",
            [{"title": "dev_sub:1:2", "mz": 400.0, "rt": 1.0, "charge": 2}],
        )
        cache_path = index_dir / CACHE_FILENAME
        assert not cache_path.is_file()
        df = load_or_build_rt_mass_cache(index_dir)
        assert len(df) == 1
        assert cache_path.is_file()

    def test_reuses_existing_cache(self, tmp_path: Path) -> None:
        index_dir = tmp_path / "pepquery_index"
        index_dir.mkdir()
        _write_mgf(
            index_dir / "100.mgf",
            [{"title": "dev_sub:1:2", "mz": 400.0, "rt": 1.0, "charge": 2}],
        )
        load_or_build_rt_mass_cache(index_dir)  # builds + writes cache
        # Add a new mgf file AFTER the cache was written, but don't touch the
        # index_dir's own mtime — simulate a stale-but-not-yet-invalidated cache
        # by directly re-reading: cache should still reflect only the first file
        # unless the directory mtime moved forward, which .mkdir()/write below does.
        df_before = pl.read_parquet(index_dir / CACHE_FILENAME)
        assert len(df_before) == 1

    def test_rebuilds_when_index_dir_newer_than_cache(self, tmp_path: Path) -> None:
        import os
        import time

        index_dir = tmp_path / "pepquery_index"
        index_dir.mkdir()
        _write_mgf(
            index_dir / "100.mgf",
            [{"title": "dev_sub:1:2", "mz": 400.0, "rt": 1.0, "charge": 2}],
        )
        load_or_build_rt_mass_cache(index_dir)
        cache_path = index_dir / CACHE_FILENAME
        # Force the cache to look older than the index dir's next modification.
        old_time = cache_path.stat().st_mtime - 10
        os.utime(cache_path, (old_time, old_time))
        time.sleep(0.01)
        _write_mgf(
            index_dir / "200.mgf",
            [{"title": "dev_sub:2:2", "mz": 500.0, "rt": 2.0, "charge": 2}],
        )
        df = load_or_build_rt_mass_cache(index_dir)
        assert len(df) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_index_rt_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.tarsus.steps._index_rt_cache'`

- [ ] **Step 3: Write the implementation**

Create `src/tarsus/steps/_index_rt_cache.py`:

```python
"""Build and cache a spectrum_title -> (file, charge, rt, mass) lookup
from the PepQuery index MGF files.

PepQuery's ``psmrankall.txt``/``ptmall.txt`` output carries an experimental
mass and charge per spectrum_title, but no retention time. Step 7's
proximity-matching logic (see
``docs/superpowers/specs/2026-07-08-step7-proximity-lineage-design.md``)
needs retention time for PepQuery/PDV-side spectra, which only exists in
the PepQuery index's own MGF files (``RTINSECONDS=``). This module scans
those files once and caches the result, since scanning ~25k small files
on every Step 7 run would be wasteful.
"""

from pathlib import Path
import polars as pl

CACHE_FILENAME = "_rt_mass_cache.parquet"
PROTON_MASS = 1.007276466


def build_rt_mass_cache(index_dir: Path) -> pl.DataFrame:
    """Scan every ``*.mgf`` file in *index_dir* and extract per-spectrum metadata.

    Returns a DataFrame with columns ``spectrum_title``, ``file_name``,
    ``charge``, ``rt_seconds``, ``mass`` (neutral monoisotopic mass,
    computed from the MGF's own ``PEPMASS``/``CHARGE``). Entries missing
    any required field, or whose title doesn't split into exactly three
    ``:``-separated parts (``file:scan:charge``), are silently skipped.
    """
    titles: list[str] = []
    file_names: list[str] = []
    charges: list[int] = []
    rts: list[float] = []
    masses: list[float] = []

    def _flush(
        title: str | None, rt: float | None, mz: float | None, charge: int | None,
    ) -> None:
        if title is None or rt is None or mz is None or charge is None:
            return
        parts = title.split(":")
        if len(parts) != 3:
            return
        neutral_mass = mz * charge - charge * PROTON_MASS
        titles.append(title)
        file_names.append(parts[0])
        charges.append(charge)
        rts.append(rt)
        masses.append(neutral_mass)

    for mgf_path in sorted(index_dir.glob("*.mgf")):
        title: str | None = None
        rt: float | None = None
        mz: float | None = None
        charge: int | None = None
        with mgf_path.open() as f:
            for raw_line in f:
                line = raw_line.strip()
                if line.startswith("TITLE="):
                    _flush(title, rt, mz, charge)
                    title = line[len("TITLE="):]
                    rt = mz = charge = None
                elif line.startswith("RTINSECONDS="):
                    rt = float(line[len("RTINSECONDS="):])
                elif line.startswith("PEPMASS="):
                    mz = float(line[len("PEPMASS="):].split()[0])
                elif line.startswith("CHARGE="):
                    charge_str = line[len("CHARGE="):].rstrip("+").rstrip("-")
                    charge = int(charge_str)
        _flush(title, rt, mz, charge)

    return pl.DataFrame({
        "spectrum_title": titles,
        "file_name": file_names,
        "charge": charges,
        "rt_seconds": rts,
        "mass": masses,
    })


def load_or_build_rt_mass_cache(index_dir: Path) -> pl.DataFrame:
    """Load the cached RT/mass lookup for *index_dir*, building it if missing or stale.

    The cache is considered stale if the index directory's own mtime is
    newer than the cache file's mtime (i.e. files were added/removed since
    the cache was written).
    """
    cache_path = index_dir / CACHE_FILENAME
    if cache_path.is_file() and cache_path.stat().st_mtime >= index_dir.stat().st_mtime:
        return pl.read_parquet(cache_path)
    df = build_rt_mass_cache(index_dir)
    df.write_parquet(cache_path)
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_index_rt_cache.py -v`
Expected: All tests PASS (7 passed).

Note on `test_rebuilds_when_index_dir_newer_than_cache`: writing a new file into `index_dir` updates the directory's mtime on Linux, which is what makes this test meaningful — confirm this holds on the target filesystem if the test is flaky (NFS mtime granularity can occasionally lag; the `os.utime` backdating of the cache file plus `time.sleep(0.01)` before the second write is there to make the ordering robust).

- [ ] **Step 5: Commit**

```bash
git add src/tarsus/steps/_index_rt_cache.py tests/unit/test_index_rt_cache.py
git commit -m "feat: add PepQuery index RT/mass cache builder for Step 7 proximity matching"
```

---

### Task 2: Proximity-matching primitives in Step 7

**Files:**
- Modify: `src/tarsus/steps/step07_analyze_outputs.py` (add functions near the top, after existing helpers around line 202)
- Test: `tests/unit/test_step07_analyze_outputs.py` (add new test classes)

**Interfaces:**
- Consumes: nothing new from Task 1 directly (these are pure functions operating on a lookup dict, decoupled from the cache module).
- Produces: `RT_TOLERANCE_SECONDS: float = 24.0`, `MASS_TOLERANCE_PPM: float = 20.0` (module constants).
- Produces: `_is_proximate(file_a: str, charge_a: int, rt_a: float, mass_a: float, file_b: str, charge_b: int, rt_b: float, mass_b: float, rt_tol: float = RT_TOLERANCE_SECONDS, mass_ppm_tol: float = MASS_TOLERANCE_PPM) -> bool`
- Produces: `_group_candidates_by_file_charge(titles: Iterable[str], rt_lookup: dict[str, tuple[str, int, float, float]]) -> dict[tuple[str, int], list[str]]`
- Produces: `_find_proximate_title(file_a: str, charge_a: int, rt_a: float, mass_a: float, candidate_titles: list[str], rt_lookup: dict[str, tuple[str, int, float, float]]) -> str | None`
- Produces: `_build_rt_lookup(cache_df: pl.DataFrame) -> dict[str, tuple[str, int, float, float]]` — maps `spectrum_title -> (file_name, charge, rt_seconds, mass)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_step07_analyze_outputs.py` (append at the end of the file):

```python
import polars as pl
from src.tarsus.steps.step07_analyze_outputs import (
    _is_proximate,
    _group_candidates_by_file_charge,
    _find_proximate_title,
    _build_rt_lookup,
    RT_TOLERANCE_SECONDS,
    MASS_TOLERANCE_PPM,
)


class TestIsProximate:
    def test_exact_match_is_proximate(self) -> None:
        assert _is_proximate("f", 2, 100.0, 800.0, "f", 2, 100.0, 800.0) is True

    def test_different_file_rejected(self) -> None:
        assert _is_proximate("f", 2, 100.0, 800.0, "g", 2, 100.0, 800.0) is False

    def test_different_charge_rejected(self) -> None:
        assert _is_proximate("f", 2, 100.0, 800.0, "f", 3, 100.0, 800.0) is False

    def test_rt_within_tolerance_accepted(self) -> None:
        assert _is_proximate("f", 2, 100.0, 800.0, "f", 2, 100.0 + 20.0, 800.0) is True

    def test_rt_outside_tolerance_rejected(self) -> None:
        assert _is_proximate("f", 2, 100.0, 800.0, "f", 2, 100.0 + 25.0, 800.0) is False

    def test_rt_exactly_at_tolerance_boundary_accepted(self) -> None:
        assert _is_proximate(
            "f", 2, 100.0, 800.0, "f", 2, 100.0 + RT_TOLERANCE_SECONDS, 800.0,
        ) is True

    def test_mass_within_tolerance_accepted(self) -> None:
        mass_a = 800.0
        mass_b = mass_a * (1 + 19e-6)  # 19 ppm away
        assert _is_proximate("f", 2, 100.0, mass_a, "f", 2, 100.0, mass_b) is True

    def test_mass_outside_tolerance_rejected(self) -> None:
        mass_a = 800.0
        mass_b = mass_a * (1 + 21e-6)  # 21 ppm away
        assert _is_proximate("f", 2, 100.0, mass_a, "f", 2, 100.0, mass_b) is False

    def test_mass_exactly_at_tolerance_boundary_accepted(self) -> None:
        mass_a = 800.0
        mass_b = mass_a * (1 + MASS_TOLERANCE_PPM * 1e-6)
        assert _is_proximate("f", 2, 100.0, mass_a, "f", 2, 100.0, mass_b) is True


class TestGroupCandidatesByFileCharge:
    def test_groups_by_file_and_charge(self) -> None:
        rt_lookup = {
            "a:1:2": ("a", 2, 10.0, 100.0),
            "a:2:2": ("a", 2, 20.0, 200.0),
            "a:3:3": ("a", 3, 30.0, 300.0),
            "b:1:2": ("b", 2, 40.0, 400.0),
        }
        groups = _group_candidates_by_file_charge(rt_lookup.keys(), rt_lookup)
        assert set(groups[("a", 2)]) == {"a:1:2", "a:2:2"}
        assert groups[("a", 3)] == ["a:3:3"]
        assert groups[("b", 2)] == ["b:1:2"]

    def test_titles_missing_from_lookup_are_skipped(self) -> None:
        rt_lookup = {"a:1:2": ("a", 2, 10.0, 100.0)}
        groups = _group_candidates_by_file_charge(["a:1:2", "unknown:9:9"], rt_lookup)
        assert list(groups.keys()) == [("a", 2)]


class TestFindProximateTitle:
    def test_finds_proximate_candidate(self) -> None:
        rt_lookup = {"a:5:2": ("a", 2, 105.0, 800.0004)}
        result = _find_proximate_title("a", 2, 100.0, 800.0, ["a:5:2"], rt_lookup)
        assert result == "a:5:2"

    def test_returns_none_when_no_candidate_proximate(self) -> None:
        rt_lookup = {"a:5:2": ("a", 2, 1000.0, 800.0)}
        result = _find_proximate_title("a", 2, 100.0, 800.0, ["a:5:2"], rt_lookup)
        assert result is None

    def test_returns_none_for_empty_candidates(self) -> None:
        result = _find_proximate_title("a", 2, 100.0, 800.0, [], {})
        assert result is None


class TestBuildRtLookup:
    def test_builds_lookup_from_cache_dataframe(self) -> None:
        cache_df = pl.DataFrame({
            "spectrum_title": ["a:1:2", "b:2:3"],
            "file_name": ["a", "b"],
            "charge": [2, 3],
            "rt_seconds": [10.0, 20.0],
            "mass": [100.0, 200.0],
        })
        lookup = _build_rt_lookup(cache_df)
        assert lookup["a:1:2"] == ("a", 2, 10.0, 100.0)
        assert lookup["b:2:3"] == ("b", 3, 20.0, 200.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_step07_analyze_outputs.py -v -k "IsProximate or GroupCandidates or FindProximateTitle or BuildRtLookup"`
Expected: FAIL with `ImportError` (names not defined in `step07_analyze_outputs`).

- [ ] **Step 3: Write the implementation**

In `src/tarsus/steps/step07_analyze_outputs.py`, add after `_extract_base_name` (after line 202) and add `from collections.abc import Iterable` to the imports at the top of the file (alongside the existing `from typing import Any`):

```python
RT_TOLERANCE_SECONDS = 24.0
MASS_TOLERANCE_PPM = 20.0


def _is_proximate(
    file_a: str, charge_a: int, rt_a: float, mass_a: float,
    file_b: str, charge_b: int, rt_b: float, mass_b: float,
    rt_tol: float = RT_TOLERANCE_SECONDS,
    mass_ppm_tol: float = MASS_TOLERANCE_PPM,
) -> bool:
    """Whether spectrum B counts as the same physical event as spectrum A.

    File name and charge must match exactly. Retention time and precursor
    mass are allowed to differ within tolerance — see
    ``docs/superpowers/specs/2026-07-08-step7-proximity-lineage-design.md``
    for why these specific values (24s, 20ppm) were chosen.
    """
    if file_a != file_b or charge_a != charge_b:
        return False
    if abs(rt_a - rt_b) > rt_tol:
        return False
    if mass_a == 0:
        return False
    ppm_diff = abs(mass_a - mass_b) / mass_a * 1_000_000
    return ppm_diff <= mass_ppm_tol


def _group_candidates_by_file_charge(
    titles: Iterable[str],
    rt_lookup: dict[str, tuple[str, int, float, float]],
) -> dict[tuple[str, int], list[str]]:
    """Group spectrum titles by (file_name, charge) for fast proximity lookup.

    Titles absent from *rt_lookup* are skipped (no RT/mass data available
    for them, so they can never be a proximity match).
    """
    groups: dict[tuple[str, int], list[str]] = {}
    for title in titles:
        info = rt_lookup.get(title)
        if info is None:
            continue
        file_name, charge, _rt, _mass = info
        groups.setdefault((file_name, charge), []).append(title)
    return groups


def _find_proximate_title(
    file_a: str, charge_a: int, rt_a: float, mass_a: float,
    candidate_titles: list[str],
    rt_lookup: dict[str, tuple[str, int, float, float]],
) -> str | None:
    """Return the first title in *candidate_titles* proximate to (file_a, charge_a, rt_a, mass_a).

    Returns None if no candidate qualifies.
    """
    for title in candidate_titles:
        info = rt_lookup.get(title)
        if info is None:
            continue
        file_b, charge_b, rt_b, mass_b = info
        if _is_proximate(file_a, charge_a, rt_a, mass_a, file_b, charge_b, rt_b, mass_b):
            return title
    return None


def _build_rt_lookup(cache_df: pl.DataFrame) -> dict[str, tuple[str, int, float, float]]:
    """Build a spectrum_title -> (file_name, charge, rt_seconds, mass) dict from the RT/mass cache."""
    return {
        row["spectrum_title"]: (row["file_name"], row["charge"], row["rt_seconds"], row["mass"])
        for row in cache_df.iter_rows(named=True)
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_step07_analyze_outputs.py -v -k "IsProximate or GroupCandidates or FindProximateTitle or BuildRtLookup"`
Expected: All new tests PASS (14 passed).

- [ ] **Step 5: Commit**

```bash
git add src/tarsus/steps/step07_analyze_outputs.py tests/unit/test_step07_analyze_outputs.py
git commit -m "feat: add proximity-matching primitives to Step 7"
```

---

### Task 3: Wire proximity matching into `analyze_outputs()`

**Files:**
- Modify: `src/tarsus/steps/step07_analyze_outputs.py:205-354` (the `analyze_outputs` function)
- Create: `tests/validation/expected/step07_proximity_fixtures/` (new fixture directory: `first_psm.tsv`, `second_psm.tsv`, `ptmall.txt`, `psmrankall.txt`, `pdv_export.txt`, `pepquery_index/100.mgf`)
- Test: `tests/validation/test_step07_analyze.py` (add proximity end-to-end test)

**Interfaces:**
- Consumes: `load_or_build_rt_mass_cache` from Task 1 (`src.tarsus.steps._index_rt_cache`); `_is_proximate`, `_group_candidates_by_file_charge`, `_find_proximate_title`, `_build_rt_lookup` from Task 2.
- Produces: `analyze_outputs(..., index_dir: Path | None = None) -> pl.DataFrame` — same as before plus one new optional parameter and one new output column `match_type` (`"exact"` or `"proximity"`).

- [ ] **Step 1: Write the failing fixture and test**

Create the fixture directory `tests/validation/expected/step07_proximity_fixtures/`. This scenario: peptide `VARIANT2` on Step 3c's own spectrum `dev_sub:1:2` (RT=100.0s, mass=800.0004) has **no exact** PepQuery/PDV evidence, but PepQuery/PDV validated the same peptide on a nearby spectrum `dev_sub:5:2` (RT=110.0s — 10s away, within the 24s tolerance; mass=800.0 — well within 20ppm) on the same file+charge. The proximity path should accept it.

`tests/validation/expected/step07_proximity_fixtures/second_psm.tsv`:
```
Spectrum	Peptide	Intensity	Protein	Charge	Protein Start	Retention	Calibrated Observed Mass
dev_sub.1.1.2	VARIANT2	80000.0	PEPTIDE2_A3R	2	1	100.0	800.0004
```

`tests/validation/expected/step07_proximity_fixtures/first_psm.tsv`:
```
Spectrum	Peptide	Prev AA	Next AA	Protein	Intensity	Retention	Charge	Protein Start	Protein End	Mapped Proteins	Hyperscore	Extended Peptide	Number of Missed Cleavages	Is Unique
dev_sub.1.1.2	PEPTIDE2	K	R	sp|P12345|PROT1	100000.0	12.5	2	10	17	sp|P12345|PROT1	0.95	KPEPTIDE2R	0	Yes
```

`tests/validation/expected/step07_proximity_fixtures/psmrankall.txt`:
```
spectrum_title	confident
dev_sub:5:2	Yes
```

`tests/validation/expected/step07_proximity_fixtures/pdv_export.txt`:
```
peptide	Spectrum_Title	ions
VARIANT2	dev_sub:5:2	[b4, b5]
```

`tests/validation/expected/step07_proximity_fixtures/ptmall.txt` (tab-separated, no header, 27 columns matching `load_ptm_details`'s expected layout — same shape as the existing `step07_fixtures/ptmall.txt` but for `dev_sub:5:2`/`VARIANT2`):
```
VARIANT2	-	1	dev_sub:5:2	2	1000.0	5.0	0.01	0.0	1000.0	500.0	0.9	1	1000	0	500	0.001	1	extra_spec	VARIANT2	2	1000.5	1000.5	5.0	0.01	0.0	Ala->Arg@3[	0.95
```

Create `tests/validation/expected/step07_proximity_fixtures/pepquery_index/100.mgf`:
```
BEGIN IONS
TITLE=dev_sub:5:2
PEPMASS=401.00728
RTINSECONDS=110.0
CHARGE=2+
100.0 1000.0
END IONS
```

(Note: `PEPMASS=401.00728` at charge 2 gives neutral mass `401.00728*2 - 2*1.007276466 = 800.0` — matching the fixture's target mass within tolerance.)

Add to `tests/validation/test_step07_analyze.py`:

```python
PROXIMITY_FIXTURES = Path(__file__).parent / "expected" / "step07_proximity_fixtures"


def test_step07_analyze_proximity_match(tmp_path):
    """A Step 3c candidate with no exact PepQuery/PDV hit is accepted via
    proximity (same file+charge, RT/mass within tolerance) when index_dir
    is supplied."""
    output_ipc = tmp_path / "subs.ipc"
    result = analyze_outputs(
        first_psm_path=PROXIMITY_FIXTURES / "first_psm.tsv",
        second_psm_path=PROXIMITY_FIXTURES / "second_psm.tsv",
        ptmall_path=PROXIMITY_FIXTURES / "ptmall.txt",
        psmrankall_path=PROXIMITY_FIXTURES / "psmrankall.txt",
        pdv_path=PROXIMITY_FIXTURES / "pdv_export.txt",
        output_ipc=output_ipc,
        index_dir=PROXIMITY_FIXTURES / "pepquery_index",
    )
    assert len(result) == 1
    assert result["dependent"][0] == "VARIANT2"
    assert result["match_type"][0] == "proximity"


def test_step07_analyze_end_to_end_still_exact_without_index_dir(tmp_path):
    """Existing exact-match behavior is unchanged when index_dir is omitted."""
    output_ipc = tmp_path / "subs.ipc"
    result = analyze_outputs(
        first_psm_path=FIXTURES / "first_psm.tsv",
        second_psm_path=FIXTURES / "second_psm.tsv",
        ptmall_path=FIXTURES / "ptmall.txt",
        psmrankall_path=FIXTURES / "psmrankall.txt",
        pdv_path=FIXTURES / "pdv_export.txt",
        output_ipc=output_ipc,
    )
    assert len(result) == 1
    assert result["match_type"][0] == "exact"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/validation/test_step07_analyze.py -v -k proximity`
Expected: FAIL — either `TypeError: analyze_outputs() got an unexpected keyword argument 'index_dir'` or `polars.exceptions.ColumnNotFoundError: match_type`.

- [ ] **Step 3: Modify `analyze_outputs()`**

In `src/tarsus/steps/step07_analyze_outputs.py`, add this import at the top of the file (alongside the existing `import polars as pl` etc.) — `_build_rt_lookup` and the other proximity helpers from Task 2 are already in this same file and need no import:

```python
from ._index_rt_cache import load_or_build_rt_mass_cache
```

Change the function signature (currently line 205-212):

```python
def analyze_outputs(
    first_psm_path: Path,
    second_psm_path: Path,
    ptmall_path: Path,
    psmrankall_path: Path,
    pdv_path: Path,
    output_ipc: Path,
    index_dir: Path | None = None,
) -> pl.DataFrame:
    """Analyze PepQuery validation outputs and produce SAAV table.

    Reads PepQuery results and FragPipe search outputs, filters confident
    SAAV candidates, and produces the subs.ipc table with abundance ratios.

    If *index_dir* (the PepQuery index directory, e.g.
    ``02_index/pepquery_index``) is supplied, a Step 3c candidate is also
    accepted when a PepQuery/PDV-validated spectrum for the same peptide is
    *proximate* to the candidate's own spectrum (same file+charge, RT/mass
    within tolerance), not only on an exact spectrum-title match. See
    ``docs/superpowers/specs/2026-07-08-step7-proximity-lineage-design.md``.
    The output gains a ``match_type`` column (``"exact"`` or ``"proximity"``).
    """
```

Replace step 5's title-membership filter (currently lines 269-277):

```python
    # Convert Spectrum to canonical title
    titles = second_all["Spectrum"].map_elements(
        _spectrum_to_title, return_dtype=pl.String,
    ).alias("spectrum_title")
    second_all = second_all.with_columns(titles)

    second_psms = second_all.filter(
        pl.col("spectrum_title").is_in(first_set | saved_set),
    )
```

with:

```python
    # Convert Spectrum to canonical title, and extract own file/charge for
    # proximity matching.
    titles = second_all["Spectrum"].map_elements(
        _spectrum_to_title, return_dtype=pl.String,
    ).alias("spectrum_title")
    file_names = second_all["Spectrum"].map_elements(
        lambda s: s.split(".")[0], return_dtype=pl.String,
    ).alias("_file_name")
    second_all = second_all.with_columns([titles, file_names])

    mass_col = (
        "Calibrated Observed Mass"
        if "Calibrated Observed Mass" in second_all.columns
        else "Observed Mass"
    )

    rt_lookup: dict[str, tuple[str, int, float, float]] = {}
    if index_dir is not None:
        cache_df = load_or_build_rt_mass_cache(index_dir)
        rt_lookup = _build_rt_lookup(cache_df)

    confident_titles = first_set | saved_set
    confident_groups = _group_candidates_by_file_charge(confident_titles, rt_lookup)

    stage1_accept: list[bool] = []
    stage1_type: list[str | None] = []
    for row in second_all.iter_rows(named=True):
        own_title = row["spectrum_title"]
        if own_title in confident_titles:
            stage1_accept.append(True)
            stage1_type.append("exact")
            continue
        if not rt_lookup or mass_col not in row or row.get("Retention") is None:
            stage1_accept.append(False)
            stage1_type.append(None)
            continue
        file_a = row["_file_name"]
        charge_a = int(row["Charge"])
        rt_a = float(row["Retention"])
        mass_a = float(row[mass_col])
        candidates = confident_groups.get((file_a, charge_a), [])
        match = _find_proximate_title(file_a, charge_a, rt_a, mass_a, candidates, rt_lookup)
        if match is not None:
            stage1_accept.append(True)
            stage1_type.append("proximity")
        else:
            stage1_accept.append(False)
            stage1_type.append(None)

    second_all = second_all.with_columns([
        pl.Series("_stage1_accept", stage1_accept),
        pl.Series("_stage1_type", stage1_type),
    ])
    second_psms = second_all.filter(pl.col("_stage1_accept"))
```

Replace step 7's two-fragment coverage filter (currently lines 290-300):

```python
    # 7. Two-fragment coverage filter
    two_fragment_psms: list[str] = []
    for dep, ions in expected.items():
        pdv_pep = pdv_export.get(dep, {})
        for spec, observed in pdv_pep.items():
            if len(set(observed) & set(ions)) > 1:
                two_fragment_psms.append(spec)

    second_psms = second_psms.filter(
        pl.col("spectrum_title").is_in(two_fragment_psms),
    )
```

with:

```python
    # 7. Two-fragment coverage filter (peptide-specific, proximity-aware)
    stage2_accept: list[bool] = []
    stage2_type: list[str | None] = []
    for row in second_psms.iter_rows(named=True):
        dep = row["dependent"]
        ions = expected.get(dep)
        pdv_pep = pdv_export.get(dep, {})
        own_title = row["spectrum_title"]
        observed = pdv_pep.get(own_title)
        if ions is not None and observed is not None and len(set(observed) & set(ions)) > 1:
            stage2_accept.append(True)
            stage2_type.append("exact")
            continue
        if ions is None or not rt_lookup or mass_col not in row or row.get("Retention") is None:
            stage2_accept.append(False)
            stage2_type.append(None)
            continue
        file_a = row["_file_name"]
        charge_a = int(row["Charge"])
        rt_a = float(row["Retention"])
        mass_a = float(row[mass_col])
        pep_groups = _group_candidates_by_file_charge(pdv_pep.keys(), rt_lookup)
        candidates = pep_groups.get((file_a, charge_a), [])
        match = _find_proximate_title(file_a, charge_a, rt_a, mass_a, candidates, rt_lookup)
        if match is not None and len(set(pdv_pep[match]) & set(ions)) > 1:
            stage2_accept.append(True)
            stage2_type.append("proximity")
        else:
            stage2_accept.append(False)
            stage2_type.append(None)

    second_psms = second_psms.with_columns([
        pl.Series("_stage2_accept", stage2_accept),
        pl.Series("_stage2_type", stage2_type),
    ])
    second_psms = second_psms.filter(pl.col("_stage2_accept"))
    second_psms = second_psms.with_columns(
        pl.when((pl.col("_stage1_type") == "exact") & (pl.col("_stage2_type") == "exact"))
        .then(pl.lit("exact"))
        .otherwise(pl.lit("proximity"))
        .alias("match_type"),
    )
    second_psms = second_psms.drop([
        "_file_name", "_stage1_accept", "_stage1_type", "_stage2_accept", "_stage2_type",
    ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/validation/test_step07_analyze.py -v`
Expected: All tests PASS, including `test_step07_analyze_proximity_match` and `test_step07_analyze_end_to_end_still_exact_without_index_dir`.

Also run the full existing suite to confirm nothing else broke:

Run: `uv run pytest tests/unit/test_step07_analyze_outputs.py tests/validation/test_step07_analyze.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tarsus/steps/step07_analyze_outputs.py tests/validation/test_step07_analyze.py tests/validation/expected/step07_proximity_fixtures/
git commit -m "feat: accept proximity-matched PepQuery/PDV evidence in Step 7"
```

---

### Task 4: Wire `index_dir` into orchestration

**Files:**
- Modify: `src/tarsus/orchestration.py:143-150`
- Test: `tests/unit/test_orchestration.py` (verify the call site passes `index_dir`)

**Interfaces:**
- Consumes: `analyze_outputs(..., index_dir: Path | None = None)` from Task 3.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_orchestration.py` currently has one test (`test_no_base_input_does_not_mark_downstream_done`) that pre-touches `07_analyze/.done`, so it never actually exercises the Step 7 call site — it skips straight past Step 7. Add a new test that lets Step 7 actually run (by NOT pre-touching its `.done`) and monkeypatches `analyze_outputs` to capture its call arguments instead of doing real work. Append to `tests/unit/test_orchestration.py`:

```python
def test_step07_call_site_passes_index_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Orchestration must pass index_dir to analyze_outputs so Step 7 can
    do proximity matching (see docs/superpowers/specs/
    2026-07-08-step7-proximity-lineage-design.md)."""
    outdir = tmp_path / "out"
    fasta = tmp_path / "protein.fasta"
    raw = tmp_path / "sample.raw"
    fasta.write_text(">p\nPEPTIDE\n")
    raw.write_text("not used by this test")

    # Pretend the pipeline successfully reached Step 6, but let Step 7 run for real.
    for step in [
        "01_mzml", "03a_first_pass", "02_index", "03b_candidates",
        "03c_second_pass", "04_psm_input", "05_pepquery", "06_aggregated",
    ]:
        _touch_done(outdir, step)

    captured_kwargs: dict = {}

    def _fake_analyze_outputs(**kwargs):
        captured_kwargs.update(kwargs)
        # Produce the minimal output run_pipeline expects to find afterward.
        kwargs["output_ipc"].parent.mkdir(parents=True, exist_ok=True)
        import polars as pl
        pl.DataFrame({"dependent": []}).write_ipc(kwargs["output_ipc"])
        return None

    monkeypatch.setattr(
        "tarsus.steps.step07_analyze_outputs.analyze_outputs",
        _fake_analyze_outputs,
    )

    # Step 8 onward will still run and hit the existing empty-input guardrail —
    # that's fine, we only care that Step 7 was called correctly before that.
    with pytest.raises(RuntimeError, match="Step 8 produced no base-rescoring input files"):
        run_pipeline(outdir, fasta, [raw])

    assert captured_kwargs.get("index_dir") == outdir / "02_index" / "pepquery_index"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestration.py -v -k index_dir`
Expected: FAIL with `AssertionError` (`captured_kwargs.get("index_dir")` is `None`, since the call site doesn't pass it yet).

- [ ] **Step 3: Update the call site**

In `src/tarsus/orchestration.py`, change (currently lines 143-150):

```python
        analyze_outputs(
            first_psm_path=outdir / "03a_first_pass" / "psm.tsv",
            second_psm_path=outdir / "03c_second_pass" / "second" / "psm.tsv",
            ptmall_path=outdir / "06_aggregated" / "ptmall.txt",
            psmrankall_path=outdir / "06_aggregated" / "psmrankall.txt",
            pdv_path=outdir / "06_aggregated" / "pdv_spectra" / "PDVExportResult.txt",
            output_ipc=_07_out / "subs.ipc",
        )
```

to:

```python
        analyze_outputs(
            first_psm_path=outdir / "03a_first_pass" / "psm.tsv",
            second_psm_path=outdir / "03c_second_pass" / "second" / "psm.tsv",
            ptmall_path=outdir / "06_aggregated" / "ptmall.txt",
            psmrankall_path=outdir / "06_aggregated" / "psmrankall.txt",
            pdv_path=outdir / "06_aggregated" / "pdv_spectra" / "PDVExportResult.txt",
            output_ipc=_07_out / "subs.ipc",
            index_dir=outdir / "02_index" / "pepquery_index",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_orchestration.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tarsus/orchestration.py tests/unit/test_orchestration.py
git commit -m "feat: wire PepQuery index_dir into Step 7 orchestration call"
```

---

### Task 5: Full local test suite + real-data validation

**Files:** None modified — verification only.

**Interfaces:** None (this task consumes everything built above).

- [ ] **Step 1: Run the complete unit + validation suite**

Run: `uv run pytest tests/unit/ tests/validation/ -q -m "not lsf"`
Expected: All PASS, no regressions.

- [ ] **Step 2: Run mypy on changed modules**

Run: `uv run mypy src/tarsus/steps/step07_analyze_outputs.py src/tarsus/steps/_index_rt_cache.py src/tarsus/orchestration.py`
Expected: `Success: no issues found`.

- [ ] **Step 3: Invalidate only the sentinels affected by this change**

Per the design spec's scope section, only `07_analyze` onward is affected — Steps 1–6 outputs are untouched and must not be rerun.

Run:
```bash
mv output/trial/07_analyze output/trial/07_analyze.bak.$(date +%s 2>/dev/null || echo manual)
mv output/trial/08_base_input output/trial/08_base_input.bak.$(date +%s 2>/dev/null || echo manual) 2>/dev/null || true
```

(Do not delete — move aside, consistent with this project's "preserve expensive outputs" convention. `date +%s` is unavailable inside workflow scripts but fine in a real shell; substitute a fixed suffix if needed.)

- [ ] **Step 4: Rerun the pipeline from Step 7**

Resume via the existing sentinel-checkpoint mechanism (Steps 1–6 `.done` files are untouched, so `tarsus run` with the same inputs/output-dir skips straight to Step 7):

Run: `tarsus run --fasta data/protein.fasta -i data/*.raw -o output/trial` (or the LSF-submitted equivalent already used in this project — see `.memory/progress.md` for the exact invocation pattern used in prior sessions).

- [ ] **Step 5: Confirm non-zero output and report the match_type split**

Once Step 7 completes:

```bash
uv run python - <<'PY'
import polars as pl
df = pl.read_ipc("output/trial/07_analyze/subs.ipc")
print("total rows:", len(df))
print(df["match_type"].value_counts())
PY
```

Expected: `total rows` > 0. Record the exact/proximity split in `.memory/progress.md` per this project's session-logging convention.

- [ ] **Step 6: Update project memory**

Add a session entry to `.memory/progress.md` recording: Option C implemented, real-data row count and match_type split, and confirmation that Steps 1–6 were untouched. Do not mark this as a new decision (D-047) unless the real-data result reveals something that changes the recommendation — if it does, record that as a new decision per this project's `.agents/project.md` convention.
