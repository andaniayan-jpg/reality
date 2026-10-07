# Evidence-bounded 3D reasoning (experimental)

`reality.reason.predict(question, obj)` keeps the earlier axial-yield API. It
also runs independent Euler buckling, simple-beam bending, circular-shaft
torsion, declared-joint, and optional fatigue screens. The legacy `outcome`,
`will_fail`, and `safety_factor` still describe **only the axial-yield screen**.
Other results have separate fields and `missing_by_mode`; a missing bending
support does not suppress a buckling estimate.

```python
result = reality.reason.predict(
    "500 N load", obj,
    load_axis="z", load_case="axial_compression", support="opposed_face",
    yield_strength_pa=200e6, yield_source="manufacturer test data",
    youngs_modulus_pa=200e9,
)
print(result.safety_factor, result.buckling_load, result.missing_by_mode)
result.export_stress_map("nominal-stress.obj")
```

Buckling uses a measured midspan cross-sectional second moment and an ideal
pin–pin Euler column. A supplied Young's modulus is preferred. Otherwise a
nominal material modulus (or 200 GPa steel-like placeholder for unknown
material) is marked as an **estimate**, not a conservative bound for every
material. No imperfections, eccentricity, connection compliance or safety
code factors are modelled. Bending requires an explicit simply-supported span
and assumes a central point load. Torsional capacity requires a near-circular
closed shaft section and source-backed yield strength; without applied torque,
`torsion_risk` remains `None`. Joint risk needs declared joint geometry area,
allowable stress and load (or a narrowly labelled vertical, compressive
direct-child weight/load screen). A declared `cycles_per_day`, tensile strength,
reference cycle count and nominal stress enable only an illustrative S–N fatigue
estimate, not a design life prediction. No reference cycle count is silently
invented.

The exported OBJ contains original triangles and extended `v x y z r g b`
vertex colours. Colours are nearest-section **nominal axial stress/yield
ratios**, not a finite-element stress distribution or resolved stress
concentrations. If stress evidence is absent, all vertices are grey and the
file carries an insufficiency comment.

```python
alternative = reality.reason.what_if(
    obj, {"material": "aluminium", "load": 1000}, "500 N load",
    load_axis="z", load_case="axial_compression", support="opposed_face",
    yield_strength_pa=200e6, yield_source="test data",
)
print(alternative.changes_applied, alternative.safety_factor_delta)

answer = reality.reason.ask(obj, "which part is weakest?")
print(answer.route, answer.structured, answer.explanation)
```

What-if changes use copy-on-write mesh edits; `load` is in **newtons** and
`wall_thickness` is in the object's declared length units. A named material
does not supply a certified mechanical grade. An explicit strength or modulus
for the original material is **not carried over** when the material changes;
the modified safety factor stays unavailable until new grade data is supplied.
If a hollowing operation reverts,
it is not listed in `changes_applied`. An installed local text model can add a
plain-language recommendation, but cannot change computed numbers. Without
it, the result uses an explicit computed fallback. `ask` routes recognizable
questions to the structured functions; otherwise it returns known object facts
without inventing a physical verdict.

`capacity` and `weakest` return `None` for thresholds/rankings that cannot be
defended from the supplied geometry, applied loads, supports and material
properties. `weakest` compares available axial, Euler buckling, bending,
torsion and declared-joint safety ratios; modes with missing evidence are
excluded, not silently treated as safe. Positive results are **nominal
screens**, never safe working loads. Geometry-only screening cannot prove
structural safety. Use qualified engineering analysis and testing for
safety-critical decisions.
