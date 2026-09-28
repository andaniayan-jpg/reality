"""Move furniture in a branch and observe a downstream reachability consequence."""

import reality

exit_marker = reality.WorldObject(
    "Exit",
    reality.Bounds((-0.1, -0.1, 0.0), (0.1, 0.1, 0.2)),
    reality.Transform(position=(6.0, 0.0, 0.0)),
)
shelf = reality.WorldObject(
    "Shelf",
    reality.Bounds((-0.5, -3.0, 0.0), (0.5, 3.0, 2.0)),
    reality.Transform(position=(3.0, 6.0, 0.0)),
)
world = reality.World([exit_marker, shelf])
person = world.agent(name="Person", height=1.75, radius=0.30)

assert person.can_reach("Exit").reachable

future = world.branch()
future.move("Shelf", y=-6.0)

assert not future.agent("Person").can_reach("Exit").reachable
assert person.can_reach("Exit").reachable  # The source world did not change.

for consequence in future.consequences():
    if consequence.what_changed == "reachable_by":
        print(consequence)
        print(consequence.reason)
