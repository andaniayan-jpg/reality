"""Programmatic navigation, reachability, clearance, and SVG debugging."""

import reality

exit_marker = reality.WorldObject(
    "Exit",
    reality.Bounds((-0.1, -0.1, 0.0), (0.1, 0.1, 0.2)),
    reality.Transform(position=(6.0, 0.0, 0.0)),
)
table = reality.WorldObject(
    "Table",
    reality.Bounds((2.5, -0.75, 0.0), (3.5, 0.75, 1.0)),
)
world = reality.World([exit_marker, table])
person = world.agent(name="Person", position=(0.0, 0.0, 0.0), height=1.75, radius=0.30)

path = person.path_to("Exit")
print("reachable:", path.reachable)
print("distance:", path.distance)
print("minimum body clearance:", path.minimum_clearance)
path.export_debug("navigation.svg")
