# Copy-on-write 3D modification (experimental)

`PhysicsObject.modify` and `PhysicsScene.modify` start a **draft**. The imported
object is never edited. Methods return the same draft for chaining; `result`
materializes it, and `export(path)` writes the materialized mesh. Deferred
commands share untouched source meshes and copy a changed mesh only once.

```python
import reality

original = reality.perceive.from_3d("assembly.glb")
draft = original.modify.scale(factor=1.5).translate(x=0.2)
print(draft.change_log)
print(draft.result.volume)
draft.export("assembly-edited.glb")
comparison = reality.diff(original, draft)
print(comparison.volume_delta, comparison.improvement_score)
```

The draft is not itself a `PhysicsObject`: use `draft.result` for revised
measurements and `draft.export(...)` for write-back. A fresh access to
`original.modify` starts a separate draft. `original.change_log` stays empty.

Available measured mesh edits: material label, uniform/nonuniform scale,
translation, axis rotation, mirroring, component removal/merge, and Trimesh
repair. Component merge concatenates named meshes; it is not a Boolean solid
union and does not resolve overlaps. `thickness(region=..., value=...)` changes only the shortest bounding
dimension of an **exactly named whole component**; it is not local wall editing.
`fix_weak_points()` applies that same labelled AABB heuristic to thin-part
candidates. Neither operation establishes load-bearing safety.

`apply(text)` accepts a validated JSON edit proposal from an installed local
model when available, otherwise handles a few unambiguous literal requests.
The proposed method and arguments are whitelisted; unknown instructions are
not applied and leave an explanation in `optimization_log`. No customer file
geometry is sent to a cloud provider by this method. A custom provider can be
injected with `interpret_edit(text) -> {"method": ..., "args": ...}`.

OBJ, STL, PLY, GLB and embedded-buffer glTF exports are implemented. Multi-part
STL/PLY is rejected because those formats cannot preserve part names. OBJ
material export writes an adjacent `.mtl` file. glTF geometry is converted to
metres from declared source units; exporting unknown-unit geometry to glTF is
rejected. A Blender helper writes `.py` plus `.gltf` and sets rigid-body mass
only when density and volume are available; Blender itself is not run.

`hollow(wall_thickness=...)` makes a sealed cavity only for validated
axis-aligned box meshes. Other meshes fail explicitly rather than getting an
unreliable shell. Not yet supported: general hollowing; verified strength/earthquake/printability
optimization; validated URDF/SDF, Godot, and ROS 2 write-back. Those operations
raise an informative `PhysicsModificationError` or record a non-applied
optimization. A generic material name supplies at most a *nominal density*,
never a verified grade or yield strength. `DiffResult.improvement_score` is
`None` without load-case and safety-factor evidence. This avoids inventing a
0–1 engineering score from visual geometry alone.
`weak_points_fixed` counts only AABB screening candidates no longer flagged;
it is not proof that a structural weakness was repaired.

Exported OBJ and glTF preserve named components and geometry, but the original
source's complete scene hierarchy, animation and non-mesh semantics cannot be
round-tripped through every target format. CAD B-reps are not silently
tessellated for this editor; use the existing CAD edit API for exact CAD work.
For edited URDF/SDF geometry, previously declared inertias and joint frames
are invalidated rather than reused as if they described the changed shape.
