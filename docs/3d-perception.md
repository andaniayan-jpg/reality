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
| IGES, IGS | Optional `reality[cad]` | B-rep surfaces/solids retained; source units currently unknown |
| URDF | Safe XML + Trimesh primitives/mesh references | Zero-joint configuration, declared joints only; local mesh paths only |
| SDF | Safe XML + Trimesh primitives/mesh references | One top-level model, declared joints only; external includes and unresolved frames rejected |
| USD, USDA, USDC | Optional `reality[usd]` | Static triangular/quad mesh geometry and hierarchy; no animation, variants, procedural materials or external assets |
| FBX, DAE, 3DS | Optional `reality[assimp]` **and native libassimp** | Imported mesh groups pass through in-memory OBJ; animation, rigging, units and non-mesh semantics unavailable; native runtime not validated in this environment |
| BLEND | Reviewable manual export script | Native Blender files are not parsed; run the generated script in Blender, then load the OBJ |

The USD adapter needs Python OpenUSD bindings; the command-line `usdcat` alone
cannot expose stage geometry to Reality. `.blend` files may contain scripts, so
Reality does not run Blender or open them automatically. File parsers should run in isolated workers with
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

`reason.predict(question, obj)` can perform a **sampled axial-yield screen**
for one watertight mesh with closed convex cross-sections. Supply a load axis,
pure axial load case, opposed-face support assumption, and a documented
yield strength. It converts a single prompt mass in kg to weight using standard
gravity, then samples 19 interior sections and computes nominal stress
`force / minimum sampled area` and safety factor `yield strength / stress`.
This does **not** model buckling, bending, fatigue, fracture or contact, and
`will_fail=False` is not a safety certification. Without the required evidence,
`will_fail` and `safety_factor` are `None` with an explicit reason.

```python
screen = reality.reason.predict(
    "will this fail under 500 kg load?", part,
    load_axis="z", load_case="axial_compression", support="opposed_face",
    yield_strength_pa=2.5e8, yield_source="your material certificate",
)
print(screen.will_fail, screen.safety_factor, screen.evidence)
```

Set `use_ai=True` to request advisory text from an installed local engine, or
inject a compatible `ModelRouter`. Model text never changes measured stress or
the screen result. `from_3d(..., enrich=True)` adds advisory `ai_notes` only.

Future adapters should preserve source transforms, units, material provenance,
assembly hierarchy and articulation, with fixture-based parity tests and
explicit loss warnings before a format is listed as supported.
