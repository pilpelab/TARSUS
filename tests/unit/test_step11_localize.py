"""Unit tests for Step 11 — PyAscore localization."""

import numpy as np
import pytest
from src.tarsus.steps.step11_localize import (
    mz_diff,
    ascore_to_probability,
    SUBSTITUTION_SHIFTS,
    get_var_mod_positions,
)


class TestMzDiff:
    def test_basic(self) -> None:
        theo_mz, delta_da, delta_ppm, delta_neutral = mz_diff("PEPTIDE", 500.0, 2)
        assert theo_mz > 0
        assert isinstance(delta_da, float)
        assert isinstance(delta_ppm, float)
        assert isinstance(delta_neutral, float)

    def exact_match(self) -> None:
        theo_mz, delta_da, _, _ = mz_diff("PEPTIDE", 500.0, 2)
        # At exact match, delta should be ~theoretical - observed
        assert abs(delta_da) < 0.01  # near zero if mass happens to be ~500

    def test_unknown_aa_raises(self) -> None:
        with pytest.raises(ValueError):
            mz_diff("PEX", 500.0, 2)

    def test_charge_one(self) -> None:
        theo_mz, _, _, _ = mz_diff("PEPTIDE", 500.0, 1)
        assert theo_mz > 0


class TestAscoreToProbability:
    def test_zero_ascore(self) -> None:
        prob = ascore_to_probability(np.float64(0.0))
        assert prob == pytest.approx(1.0)

    def test_positive_ascore(self) -> None:
        prob = ascore_to_probability(np.float64(10.0))
        assert prob < 1.0
        assert prob > 0.0

    def test_large_ascore(self) -> None:
        prob = ascore_to_probability(np.float64(20.0))
        assert prob == pytest.approx(0.01, rel=0.01)


class TestSubstitutionShifts:
    def test_ala_to_gly(self) -> None:
        # A: 71.03711, G: 57.02146
        shift = SUBSTITUTION_SHIFTS["A"]["G"]
        assert abs(shift - (57.02146 - 71.03711)) < 0.001

    def test_not_self(self) -> None:
        assert "A" not in SUBSTITUTION_SHIFTS["A"]

    def test_all_amino_acids(self) -> None:
        for aa in AA_MONO:
            assert aa in SUBSTITUTION_SHIFTS


AA_MONO = {
    "A": 71.03711, "R": 156.10111, "N": 114.04293, "D": 115.02694,
    "C": 103.00919, "E": 129.04259, "Q": 128.05858, "G": 57.02146,
    "H": 137.05891, "I": 113.08406, "L": 113.08406, "K": 128.09496,
    "M": 131.04049, "F": 147.06841, "P": 97.05276, "S": 87.03203,
    "T": 101.04768, "W": 186.07931, "Y": 163.06333, "V": 99.06841,
}


class TestGetVarModPositions:
    def test_no_modifications(self) -> None:
        positions = get_var_mod_positions(
            "PEPTIDE", 0.0,
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.float32),
            0.05,
        )
        assert positions == []

    def test_simple_mod_match(self) -> None:
        # Simulate a best_seq with one [mass] annotation
        mod_mass = 15.9949
        positions = get_var_mod_positions(
            f"P[+{mod_mass:.4f}]EPTIDE", mod_mass,
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.float32),
            0.05,
        )
        assert positions == [1]

    def test_with_aux_mod(self) -> None:
        mod_mass = 15.9949
        # P has var mod + aux mod at same position
        positions = get_var_mod_positions(
            f"P[+{mod_mass * 2:.4f}]EPTIDE", mod_mass,
            np.array([1], dtype=np.uint32),
            np.array([mod_mass], dtype=np.float32),
            0.05,
        )
        # total mass = 15.9949*2 = 31.9898, aux = 15.9949, var = 31.9898-15.9949 = 15.9949
        assert 1 in positions

    def test_too_large_tolerance_excludes(self) -> None:
        mod_mass = 15.9949
        positions = get_var_mod_positions(
            f"P[+{mod_mass:.4f}]EPTIDE", mod_mass + 1.0,
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.float32),
            0.05,
        )
        assert positions == []

    def test_unbalanced_brackets(self) -> None:
        with pytest.raises(ValueError, match="Unbalanced brackets"):
            get_var_mod_positions(
                "P[EPTIDE", 0.0,
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.float32),
                0.05,
            )
