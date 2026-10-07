from __future__ import annotations

import reality


def test_runtime_version_matches_the_declared_distribution_version() -> None:
    assert reality.__version__ == "0.2.2"
