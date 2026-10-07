# reality

`reality` is a typed Python toolkit for loading 3D/CAD assets and asking
deterministic spatial questions about them. It preserves source geometry where
the selected backend supports it, while returning structured evidence and
explicit uncertainty rather than invented physical facts. Optional AI features
provide advisory text only; geometry and physics results remain separate.

## Install

```bash
python -m pip install reality
```

## Quick examples

### Ask the copilot

```python
import reality

answer = reality.copilot("What should I inspect before loading a shelf?")
print(answer)
```

The copilot uses a configured local or hosted AI provider. If none is ready, it
returns an honest setup message instead of inventing an answer.

### Read a 3D model

```python
import reality

obj = reality.perceive.from_3d("file.obj", units="m")
print(obj.summary)
print(obj.bounds)
print(obj.estimated_mass)  # Available only with known units and density evidence.
```

### Screen a supplied load case

```python
import reality

obj = reality.perceive.from_3d("bracket.obj", units="m")
prediction = reality.reason.predict(
    "will this fail under 500 kg?",
    obj,
    load_axis="z",
    load_case="axial_compression",
    support="opposed_face",
    yield_strength_pa=250_000_000,
    yield_source="material certificate",
)
print(prediction.will_fail, prediction.safety_factor)
```

## Optional extras

```bash
python -m pip install "reality[video]"   # File-only MP4 frame extraction
python -m pip install "reality[assimp]"  # FBX, DAE, and 3DS import support
python -m pip install "reality[cad]"     # STEP, STP, and IGES B-rep support
```

## What it includes

- OBJ, STL, PLY, GLB, and glTF reading through Trimesh.
- Optional CAD, Assimp, USD, video, GPU, and physics integrations.
- Spatial `World` queries, relationship graphs, copy-on-write branches, and
  consequence analysis.
- Structured 3D interpretation through `reality.perceive.from_3d()`.
- Bounded physical screening and editing workflows that keep source geometry
  immutable unless an explicit edit is committed.

## Honest limitations

- Mesh operations primarily use axis-aligned bounds; they are not general
  triangle-mesh collision detection or finite-element analysis.
- A generic material name does not establish an engineering grade or yield
  strength. Supply traceable material properties for load screening.
- Optional integrations require their own installed backends. Reality never
  silently installs applications, downloads models, or uploads files.
- Image and video features produce observations, not calibrated metric geometry
  or a verified digital twin.
- The built-in simulation fallback is an approximate Euler/AABB model. Use a
  validated backend and domain review for safety-critical work.

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff format --check .
ruff check .
python -m mypy src/reality
```

Licensed under [Apache-2.0](LICENSE).
