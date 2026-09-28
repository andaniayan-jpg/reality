"""List known graph relationships for an object."""

import reality

world = reality.load("room.glb")

for relationship in world.relationships("Cup"):
    print(f"{relationship.source.name} --{relationship.type.value}--> {relationship.target.name}")
