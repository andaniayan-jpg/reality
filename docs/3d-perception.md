# File-based 3D perception

`reality.perceive.from_3d(path)` builds a `PhysicsObject` from the existing
`RealityModel`. It retains the original mesh references or CAD B-reps, part
names, hierarchy, transforms and Reality Graph. Geometry and units are parsed
without an AI model. `obj.model`, `obj.graph`, `obj.world`, `obj.parts`, and
delegated `measure`, `distance`, `clearance`, `intersections`, `contains`, and
`topology` let callers reuse the established deterministic APIs.

| Format | Current path | Important limit |
| --- | --- | --- |
| OBJ, STL, PLY | Trimesh | No declared linear units; supply `units` for SI mass |
| GLB, glTF | Trimesh | Uses glTF metre convention; mesh geometry is not CAD topology |
| STEP, STP | Optional `reality[cad]` | B-rep retained; STEP units reported; no inferred joints |
| URDF | Safe XML + Trimesh primitives/mesh references | Zero-joint configuration, declared joints only; local mesh paths only |
| FBX, DAE, 3DS, USD/USDA/USDC, SDF, IGES, BLEND | Not implemented | Raises `ModelFileError`, never silently approximates format semantics |

Open3D advertises additional import support, but its experimental USD import
only retains mesh/material information, not full animation or stage semantics.
Native `.blend` parsing would require Blender and handling a script-capable
file. These formats need separate validated adapters before they can be
advertised as supported. File parsers should run in isolated workers with
timeouts for untrusted uploads; the synchronous package hook does not enforce
a hard timeout.

## Physical meaning

- `volume` requires a closed mesh or CAD solid for **every** part. STL triangle
  records are welded on import so closed solids can be recognized.
- `surface_area` and `face_areas` come from mesh triangles or CAD faces.
  Nonuniformly scaled mesh surface area is currently unavailable.
- `centre_of_mass` is the geometric volume centroid under a **uniform-density**
  assumption. A real heterogeneous material distribution may shift it.
- `estimated_mass` is available only when volume and units are known and a
  positive `density_kg_m3` is supplied, or a part name consistently contains
  a recognized material token (`steel`, `aluminum`/`aluminium`). Name-based
  density is a nominal guess, reported through `material_source` and
  `limitations`, not a certified material fact. PBR colors are not treated as
  physical material properties.
- `moment_of_inertia` is a 3×3 SI tensor (kg·m²) about the aggregate volume
  centroid only for closed mesh parts with known units and uniform density.
  CAD inertia remains unavailable pending a validated OCP adapter.
- `weak_points` currently screens only whole-part AABB aspect ratios. A thin
  bounding extent can warrant inspection, but does not establish a weak wall,
  overhang, stress concentration, or failure. An empty list is not proof of
  safety.
- `balance` is `"unknown"` without a support surface and load case.
- `joints` contains explicit URDF declarations. Cylinders in arbitrary meshes
  are not automatically labelled hinges.

```python
import reality

robot = reality.perceive.from_3d("robot.urdf", density_kg_m3=1000)
for joint in robot.joints:
    print(joint.name, joint.type, joint.parent, joint.child, joint.axis)

# For OBJ/STL/PLY, the coordinate unit must come from the caller:
part = reality.perceive.from_3d("part.obj", units="mm", density_kg_m3=2700)
print(part.estimated_mass)
```

`reason.predict(question, obj)` returns an evidence-bounded `Prediction` whose
outcome is currently `unknown`; it cannot calculate load failure from geometry
alone. Set `use_ai=True` to request advisory text from an installed local
Ollama model, or inject a compatible `ModelRouter`. Model text never changes
the physical outcome or measured fields. `from_3d(..., enrich=True)` similarly
adds `ai_notes` only. Neither API runs finite-element analysis.

Future adapters should preserve source transforms, units, material provenance,
assembly hierarchy and articulation, with fixture-based parity tests and
explicit loss warnings before a format is listed as supported.
