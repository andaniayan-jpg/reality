# Deterministic model editing

`RealityModel.edit()` opens a local, copy-on-write transaction. Imported source
geometry is never changed. A committed edit produces a new immutable
`RealityModel` and a typed history with measurements before and after each
operation.

```python
import reality

model = reality.open("bracket.step")
result = (
    model.edit()
    .hole("bracket", radius=3.0, depth=20.0)
    .fillet("bracket", radius=0.5, edge_indices=[2, 4])
    .commit()
)

assert result.validate().valid
result.export("bracket-revised.step")
```

An edit session provides `preview()`, `undo()`, `redo()`, `commit()`, and
`rollback()`. `EditResult.history` is an ordered tuple of `EditOperation`
records containing target IDs, parameters, before/after volume, surface area,
and bounds evidence. `EditResult.validate()` reports backend validation errors
and warnings instead of silently declaring an uncertain topology fact.

## Supported operations

CAD operations run against the source B-rep through CadQuery/OpenCascade and
preserve a B-rep result: `translate`, `rotate`, `scale`, `offset`, `union`,
`subtract`, `intersect`, `hole`, `pocket`, `extrude`, `fillet`, `chamfer`, and
`shell`. Select faces or edges first with `select_faces()` or `select_edges()`,
or supply their indices directly to the relevant feature. OpenCascade may
reject geometrically impossible feature sizes; Reality returns an
`EditOperationError` with the failure instead of substituting an approximation.

Mesh operations run through Trimesh and retain mesh semantics: `translate`,
`rotate`, `scale`, `delete`, `rename`, `merge`, `split`, `crop`, `simplify`,
`repair`, and `normals`. CAD-only operations deliberately reject mesh targets;
Reality does not pretend a triangle mesh has exact CAD topology.

## Export and semantic boundaries

Export the committed `result.model`, not the original source. STEP export is
available only when the result retains B-rep solids. GLB and STL are mesh
exports. CAD-to-mesh export uses the existing explicit loss warnings: B-rep
topology, parametric feature history, and some assembly semantics cannot be
recovered from a mesh.

## Hosted edit jobs

The hosted API accepts a declarative operation plan and runs the same package
editor in an asynchronous job:

```bash
curl -X POST "https://api.reality.dev/v1/models/$MODEL_ID/edits" \
  -H "Authorization: Bearer $REALITY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operations":[{"operation":"translate","parameters":{"target":"housing","x":2.0}}]}'
```

Poll the returned edit job at `GET /v1/edits/{job_id}`. A successful job has a
new `result_model_id`; the source model remains intact and tenant-scoped. The
dashboard playground displays the source and edited result side by side, but
those WebGL previews are not the authoritative measurement engine.
