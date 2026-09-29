"""Optional learned candidate prioritization backed by exact Reality verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray


class PredictorUnavailableError(ImportError):
    """Raised when the optional ``reality[learn]`` dependency is not installed."""


@dataclass(slots=True)
class CandidatePrioritizer:
    """A learned proposal order; every finalist still requires exact Reality evaluation."""

    model: Any

    @classmethod
    def train(
        cls,
        features: NDArray[np.floating[Any]],
        targets: NDArray[np.floating[Any]],
        *,
        random_state: int = 0,
    ) -> CandidatePrioritizer:
        """Train an optional regressor from Reality-generated ground truth."""
        try:
            from sklearn.ensemble import RandomForestRegressor  # type: ignore[import-untyped]
        except ImportError as error:  # pragma: no cover - optional dependency
            raise PredictorUnavailableError(
                "Install reality[learn] to train a predictor."
            ) from error
        matrix = _features(features)
        values = np.asarray(targets, dtype=np.float64)
        if values.shape != (matrix.shape[0],):
            raise ValueError("targets must have shape (samples,)")
        model = RandomForestRegressor(n_estimators=100, random_state=random_state, n_jobs=-1)
        model.fit(matrix, values)
        return cls(model)

    def predict(self, features: NDArray[np.floating[Any]]) -> NDArray[np.float64]:
        """Predict proposal scores only; do not treat these as exact results."""
        return np.asarray(self.model.predict(_features(features)), dtype=np.float64)

    def prioritize(self, features: NDArray[np.floating[Any]]) -> NDArray[np.int64]:
        """Return descending predicted-score indices with a stable index tie-breaker."""
        scores = self.predict(features)
        indices: NDArray[np.int64] = np.arange(scores.size, dtype=np.int64)
        return cast(NDArray[np.int64], np.asarray(np.lexsort((indices, -scores)), dtype=np.int64))


def _features(value: NDArray[np.floating[Any]]) -> NDArray[np.float64]:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or not np.all(np.isfinite(matrix)):
        raise ValueError("features must be a non-empty finite 2D array")
    return matrix
