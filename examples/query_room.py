"""Load a room and inspect typed spatial queries."""

import reality

world = reality.load("room.glb")

distance = world.distance("Chair", "Table")
print(f"chair/table separation: {distance.distance} {distance.units}")
print("chair is in room:", world.inside("Chair", "Room").value)
