"""Step-07/11 regression eval: re-run the two deterministic analysis steps on
frozen reference slices and fail if a commit silently changes the output or
breaks reproduction of Slava.

Two gates per fixture (see docs/superpowers/specs/2026-07-28-step07-11-...):

1. **Snapshot** - a fresh ``analyze_outputs`` / ``localize`` over the committed
   slice must equal the committed golden (canonicalized: sorted, floats rounded).
2. **Invariants** - schema, no ``rev_`` decoy leak, non-null MSBooster scores,
   finite ``dpbp``, and substitution-identity + ``dpbp`` correlation against
   Slava's reference on the shared spectra.

Regenerating goldens on an intentional change: ``TARSUS_EVAL_UPDATE=1``. See
``tests/eval/README.md`` - blessing is a reviewed commit, never blind.

Runs in seconds: no cluster, no external tools, no network.
"""
from __future__ import annotations

import os

import polars as pl
import pytest

from tarsus.steps.step07_analyze_outputs import analyze_outputs
from tarsus.steps.step11_localize import localize
from tests.eval import eval_lib as L

UPDATE = os.environ.get("TARSUS_EVAL_UPDATE") == "1"


@pytest.fixture(scope="module", params=L.FIXTURES)
def result(request, tmp_path_factory):
    """Fresh step-07 and step-11 outputs for one fixture, computed once.

    Step 11 runs on the committed golden ``subs.ipc`` (its declared input), so
    the two steps are snapshot-tested independently. Under ``TARSUS_EVAL_UPDATE``
    the goldens are rewritten instead of asserted.
    """
    name = request.param
    inp = L.fixture_inputs(name)
    gold = L.fixture_golden(name)
    tmp = tmp_path_factory.mktemp(f"eval_{name}")

    subs = analyze_outputs(
        first_psm_path=inp["first_psm"],
        second_psm_path=inp["second_psm"],
        ptmall_path=inp["ptmall"],
        psmrankall_path=inp["psmrankall"],
        pdv_path=inp["pdv"],
        output_ipc=tmp / "subs.ipc",
        sample=name,
    )
    if UPDATE:
        subs.write_ipc(gold["subs"])

    localized = localize(
        subs_ipc=gold["subs"],  # step 11's declared input is the golden subs.ipc
        psmrankall_path=inp["psmrankall"],
        psmrankall_base_path=inp["psmrankall_base"],
        spectra_mgf=inp["mgf"],
        output_ipc=tmp / "subs_localized.ipc",
        output_csv=tmp / "subs_localized.csv",
    )
    if UPDATE:
        localized.write_ipc(gold["subs_localized"])
        localized.write_csv(gold["subs_localized_csv"])

    return {"name": name, "subs": subs, "localized": localized}


def test_step07_snapshot(result):
    """Fresh step-07 output equals the committed golden subs.ipc."""
    if UPDATE:
        pytest.skip("TARSUS_EVAL_UPDATE=1: goldens rewritten, not asserted")
    golden = pl.read_ipc(L.fixture_golden(result["name"])["subs"])
    L.assert_snapshot_equal(result["subs"], golden)


def test_step07_invariants(result):
    """Schema, decoy, score-null, and dpbp-finiteness guards on step-07 output."""
    L.run_all_invariants(result["subs"])


def test_step07_matches_slava(result):
    """Substitution identity == 100% and dpbp Pearson r >= 0.99 vs the reference."""
    ref = pl.read_ipc(L.fixture_reference(result["name"]))
    L.slava_compare(result["subs"], ref).assert_ok()


def test_step11_snapshot(result):
    """Fresh step-11 output equals the committed golden subs_localized.ipc."""
    if UPDATE:
        pytest.skip("TARSUS_EVAL_UPDATE=1: goldens rewritten, not asserted")
    golden = pl.read_ipc(L.fixture_golden(result["name"])["subs_localized"])
    L.assert_snapshot_equal(result["localized"], golden)


def test_step11_nonempty(result):
    """Step 11 localizes at least one substitution on the slice."""
    assert result["localized"].height > 0
