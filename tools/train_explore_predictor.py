"""Train the optional proposal model; use exact Reality checks on every finalist."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from reality.experimental import CandidatePrioritizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reality_prioritizer.joblib"))
    args = parser.parse_args()
    try:
        import joblib
    except ImportError as error:  # pragma: no cover - optional dependency
        raise SystemExit("Install reality[learn] to train a predictor.") from error
    data = np.load(args.dataset)
    model = CandidatePrioritizer.train(data["features"], data["targets"], random_state=42)
    joblib.dump(model, args.output)
    print({"output": str(args.output), "samples": int(data["features"].shape[0])})


if __name__ == "__main__":
    main()
