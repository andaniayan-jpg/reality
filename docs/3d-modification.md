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

URDF and SDF write-back preserves imported link and joint names, along with
unchanged inertial XML. Changed meshes are written as link-local OBJ sidecars;
their inertias are recomputed from an explicit density, nominal named-material
density, or an effective density inferred from a source link's declared mass and
closed volume. If that evidence is absent, export fails instead of reusing stale
inertias. Converting a non-robot mesh generates a labelled robot file with one
link per component and fixed joints; it also requires known units and density.
This is zero-pose geometry write-back, **not** a full URDF/SDF frame-graph or
dynamics round-trip. External includes, animation, plugin semantics and joint
limits are not inferred during cross-format conversion.

`obj.export.to_godot("scene.tscn")` writes a Godot 4 scene and adjacent GLB
visuals. Each component has a `RigidBody3D` with an **approximate AABB** box
collider and an imported GLB `PackedScene` visual containing its
`MeshInstance3D`. The scene uses default friction 0.5, bounce 0.0, and mass
1 kg only when corresponding physical properties are unavailable. A GLB is a
scene resource in Godot, not a `Mesh`, so it cannot be assigned directly to
`MeshInstance3D.mesh`. Godot itself is not run in the test suite.

`obj.export.to_ros2("robot_node.py")` writes an AST-validated ROS 2 Python node
and a URDF sidecar. It publishes `robot_description` and zero-pose
`/joint_states`. For a `base_link`, it subscribes to `/cmd_vel`, but does not
move hardware or a simulator. Running through `ros2 run` requires registering
the generated node as a console entry point in a ROS 2 package. ROS 2 itself
is not run in the test suite.

`hollow(wall_thickness=...)` makes a sealed cavity for boxes and other verified
convex meshes using inward-offset convex hull planes. Trimesh does **not**
provide a general `offset_mesh` function in the tested release. Concave,
nonmanifold or otherwise unverifiable shapes are left unchanged with a revert
entry in `change_log`; an unrelated AABB cavity is never substituted.

`optimize_for("balanced")` translates the geometric centre of mass to the AABB
centre. `minimum_weight`, `printable` and `earthquake_safe` currently record
why no edit was made: a mesh alone lacks a certified load case, yield strength,
support conditions, print orientation or seismic anchorage. There is no
validated iterative safety-factor loop, support generation or earthquake brace
design. A generic material name supplies at most a *nominal density*, never a
verified grade or yield strength.

`DiffResult.improvement_score` uses only supplied evidence: a reduction in
screening weak-point candidates, explicit old/new safety factors, and measured
mass reduction for a minimum-weight goal. Available terms are reweighted; with
no usable evidence the score stays `None`. A positive score is not a structural
safety certificate.
`weak_points_fixed` counts only AABB screening candidates no longer flagged;
it is not proof that a structural weakness was repaired.

Exported OBJ and glTF preserve named components and geometry, but the original
source's complete scene hierarchy, animation and non-mesh semantics cannot be
round-tripped through every target format. CAD B-reps are not silently
tessellated for this editor; use the existing CAD edit API for exact CAD work.
For edited URDF/SDF geometry, the materialized `PhysicsObject` invalidates its
in-memory declared inertia and joint-frame annotations. Export write-back uses
the retained source XML for original names/frames and recomputes changed inertial
blocks when adequate density evidence exists.
