"""Ask whether an object has deterministic AABB-based line of sight."""

import reality

world = reality.load("room.glb")
result = world.visible("Television", from_="Sofa")

print("visible:", result.value)
print("sample visibility:", result.visibility_fraction)
print("occluders:", [object_.name for object_ in result.occluding_objects])
print("reason:", result.reason)
