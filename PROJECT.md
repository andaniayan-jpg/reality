# Project

## Vision

Make physical 3D worlds a first-class programmable object in Python.

## Core differentiation

Reality is not only a geometry-query wrapper. Its central abstraction is a physical world that can be snapshotted, branched into alternate states, changed without mutating its source, and compared for consequences. This supports questions such as “what spatial facts change if this shelf moves?” using deterministic geometry and structured evidence.

Branches share immutable objects, mesh references, snapshot indexes, and unaffected Reality Graph edges. They store only changed objects, change records, graph invalidations, and recalculated edges. This persistent-state design makes many alternate worlds practical without copying a scene’s geometry for every hypothesis.

Consequence analysis evaluates the dependency frontier created by branch changes. Direct consequences involve a changed object; downstream consequences currently include visibility changes caused by an object moving into or out of a sight line. Results are typed, iterable, and JSON-serializable for use by higher-level systems without requiring AI.

Agents and navigation add a second downstream reasoning layer: the same world can be evaluated for a human, wheelchair, game character, robot, or vehicle using only physical dimensions. Cached reachability queries participate in branch invalidation, so moving an obstacle can produce a structured downstream consequence such as `reachable -> unreachable` without changing the source world.

Explicit articulation extends alternate-world reasoning to physical affordances such as a
door sweep or drawer extension. Replaceable simulation backends add observed dynamics
without making Reality itself a physics engine. Batched delta arrays are the scale path
for evaluating many alternate worlds; GPU work is accepted only after CPU-reference
correctness and actual-device benchmarks.

Imported physical meaning is deliberately explicit and portable. A scene can carry a
small Reality metadata document in glTF/GLB extras or a sidecar file to declare units,
joints, and rigid-body properties. Reality validates that document and resolves it to
already-loaded objects; it never guesses a hinge or material from mesh names. The MuJoCo
reference backend reuses compiled topology while allocating fresh state for each run, so
CPU simulation is faster for repeated scenarios without compromising branch isolation.

## Foundation milestone

This repository establishes the stable core: scene loading, value objects, object lookup, deterministic spatial predicates, a dependency-aware Reality Graph, persistent world branches, and consequence comparison. It provides a clean seam for future rendering, exact-geometry, semantic, and simulation backends without exposing any one of them in the public API.

## Non-goals for this milestone

AI, natural-language querying, Blender integration, and unvalidated GPU claims remain out
of scope. Navigation, articulation, branchable worlds, CPU physics, and CPU batched
evaluation are now implemented foundations.

## Principles

1. Correct, explainable results over clever inference.
2. A small public API that is pleasant to type-check and test.
3. Backend adapters belong at the edge; public value types belong at the core.
4. New capabilities must be additive and preserve deterministic baseline behavior.
