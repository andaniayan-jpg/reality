"""Read a STEP model while retaining its CAD topology."""

from __future__ import annotations

import sys

import reality


def main(path: str) -> None:
    model = reality.open(path)
    print(model.summary())
    for part in model.parts:
        print(part.name, part.volume, part.topology())


if __name__ == "__main__":
    main(sys.argv[1])
