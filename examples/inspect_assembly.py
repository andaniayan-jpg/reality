"""Inspect deterministic structural relationships in an imported assembly."""

from __future__ import annotations

import sys

import reality


def main(path: str) -> None:
    model = reality.open(path)
    print(model.summary())
    for assembly in model.assemblies:
        print(f"assembly {assembly.name}: {assembly.part_ids}")
    for result in model.intersections():
        if result.value:
            print("AABB intersection:", [part.name for part in result.objects], result.evidence)


if __name__ == "__main__":
    main(sys.argv[1])
