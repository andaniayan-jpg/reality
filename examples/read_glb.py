"""Read a GLB scene using the structural model API."""

from __future__ import annotations

import sys

import reality


def main(path: str) -> None:
    model = reality.open(path)
    print(model.summary())
    print(model.validate())


if __name__ == "__main__":
    main(sys.argv[1])
