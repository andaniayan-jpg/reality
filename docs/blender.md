# Blender integration

Reality's first Blender boundary is deliberately narrow. It is intended to run
inside Blender's own Python environment, where the optional `bpy` module is
available. `pip install reality` does not install Blender or a substitute
`bpy` package.

```python
import reality

adapter = reality.BlenderSceneIntegration()
print(adapter.status())

# In Blender only:
world, evidence = adapter.read_active_scene()
preview = adapter.preview_transforms(world)
# Review `preview.changes` in your UI first.
adapter.apply_transforms(preview, confirmed=True)
```

The adapter reads active-scene mesh object bounds and transforms. It keeps a
direct reference to Blender mesh data but uses Reality's existing `World` and
predicate implementation for spatial operations.

Safety boundaries:

- It never opens or saves arbitrary `.blend` files.
- It does not execute Blender text blocks, add-ons, drivers, or project scripts.
- It previews all transform writes and requires `confirmed=True` to apply them.
- It checks the scene has not changed since preview, and rolls its own prior
  writes back if a later write fails.
- It does not claim fidelity for mesh editing, modifiers, materials,
  animation, constraints, collection hierarchy, or coordinate conversion.

Run the inspection operator from Blender after registering it:

```python
import reality
reality.register_addon()
```

The required native-host validation has not yet been performed in this
repository. Until a specified Blender version runs this adapter in CI or has a
recorded manual validation, Blender support remains experimental and V3 remains
partial.
