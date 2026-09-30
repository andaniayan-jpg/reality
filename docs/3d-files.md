# Reality v2 3D and CAD files

`reality.open()` reads a structural model. It is distinct from the v0.1
`reality.load()` API, which continues to produce a mutable spatial `World`.

```python
import reality

model = reality.open("motor.step")
print(model.summary())
print(model.topology())
print(model.clearance("solid-1", "solid-2"))
```

Supported mesh formats are OBJ, STL, PLY, GLB and glTF, backed by Trimesh.
STEP and STP are available with `pip install "reality[cad]"`, backed by
CadQuery/OCP. STEP solids remain B-rep objects: faces, edges, vertices, shells
and solids are exposed directly from the CAD backend. Requesting `part.mesh`
creates a tessellated interoperability view; it does not replace `part.solid`.

## Units and precision

Reality reports source units rather than silently inventing them. glTF uses its
format convention of metres. OBJ, STL and PLY have no standard declared linear
unit, so their unit is `"unknown"`. STEP SI millimetres and metres are read from
the file declaration; unsupported/missing declarations remain `"unknown"`.

Use `model.to_units("m")` only when the source unit is known. The current
inspection predicates use deterministic axis-aligned bounds and explicitly say
`approximation: AABB` in their evidence. They are useful broad-phase facts, not
claims of exact curved-surface clearance or B-rep containment.

## Safety

`reality.open(path, max_bytes=...)` validates extensions and format markers
before parsing, rejects malformed content, and does not execute file scripts.
glTF JSON is parsed as data. The API accepts a `parser_hook(path, stage)` for
service orchestration; production services that need a hard parse timeout
should run CAD parsing in a separate worker process, because an in-process CAD
kernel cannot be safely force-cancelled across all supported platforms.

No archive formats are accepted today, so ZIP/archive-bomb inputs (such as 3MF)
are not unpacked. 3MF, IGES, USD and IFC are intentionally future backend
adapters, not falsely advertised as supported.

## Export

`model.export("output.glb")` and `model.export("output.stl")` export mesh data.
For a CAD model this tessellates its solids and emits a warning because exact
B-rep topology, labels and assembly metadata are lost. `model.export("copy.step")`
is allowed only for a CAD model whose parts have B-rep solids. Mesh-to-STEP is
refused because it would fabricate CAD semantics.
