"""Create, edit, validate, and export a small CAD model using Reality.

Requires the optional CAD adapter: ``python -m pip install -e '.[cad]'``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import reality


def main() -> None:
    try:
        import cadquery as cq
    except ImportError as error:
        raise SystemExit("This example requires: python -m pip install 'reality[cad]'") from error

    with tempfile.TemporaryDirectory(prefix="reality-edit-example-") as directory:
        source = Path(directory) / "bracket.step"
        output = Path(directory) / "bracket-edited.step"
        cq.exporters.export(cq.Workplane("XY").box(30, 20, 8).val(), str(source), "STEP")

        result = (
            reality.open(source)
            .edit()
            .hole("solid-1", radius=3.0, depth=12.0)
            .offset("solid-1", 0.15)
            .commit()
        )
        validation = result.validate()
        result.export(str(output))
        print(
            json.dumps(
                {
                    "valid": validation.valid,
                    "history": [operation.operation for operation in result.history],
                    "output_exists": output.exists(),
                    "volume": result.model.parts[0].volume,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
