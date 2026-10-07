from __future__ import annotations

import pytest

from reality import DiffResult


def test_improvement_score_renormalizes_only_measured_terms() -> None:
    scored = DiffResult(
        (),
        -2.0,
        None,
        1,
        None,
        weak_points_original=2,
        old_safety_factor=2.0,
        new_safety_factor=3.0,
        goal="minimum_weight",
        mass_reduction_pct=10,
    )
    assert scored.improvement_score == pytest.approx(0.42)
    weak_only = DiffResult((), None, None, 1, None, weak_points_original=2)
    assert weak_only.improvement_score == pytest.approx(0.5)
    unknown = DiffResult((), None, None, None, None)
    assert unknown.improvement_score is None
