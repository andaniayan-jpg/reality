# Reality Audit

## 1. Environment

- Python: `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`
- OS: `Windows-10-10.0.26200-SP0`
- CPU: `Intel64 Family 6 Model 170 Stepping 4, GenuineIntel`
- GPU: `cpu`
- CUDA availability: `False`
- Warp version: `1.17.0`
- NumPy: `2.2.6`
- Trimesh: `5.1.0`
- MuJoCo: `3.14.0`
- pytest: `9.0.3`
- Ruff: `0.12.10`
- MyPy: `1.17.1`
- audit UTC timestamp: `2026-09-27T08:35:24Z`

Warp probe reason: CUDA driver/device is unavailable.

## 2. Repository

- commit: `unavailable (not a Git checkout)`
- git_status: `unavailable`
- source_files: `15`
- source_loc: `3903`
- test_loc: `971`
- version: `0.1.0`

## 3. Public API Smoke Test

These operations were executed against real programmatic scenes and a temporary OBJ.

```json
{
  "reality.load": {
    "status": "PASS",
    "result": "(WorldObject(name='triangle.obj', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 0.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, -0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='triangle.obj', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))),)"
  },
  "distance": {
    "status": "PASS",
    "result": "PredicateResult(value=1.0, measurement=1.0, units='m', reason='Euclidean separation between world-axis-aligned bounding boxes.', objects=(WorldObject(name='Chair', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-1', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), evidence=mappingproxy({'bounds_a': Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), 'bounds_b': Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0))}))"
  },
  "intersects": {
    "status": "PASS",
    "result": "PredicateResult(value=False, measurement=None, units=None, reason='Bounding boxes are disjoint.', objects=(WorldObject(name='Chair', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-1', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), evidence=mappingproxy({'bounds_a': Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), 'bounds_b': Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0))}))"
  },
  "visible": {
    "status": "PASS",
    "result": "PredicateResult(value=False, measurement=3.0, units='m', reason='Every deterministic target sample is blocked by scene geometry.', objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Viewer', local_bounds=Bounds(minimum=(-2.0, 0.0, 0.0), maximum=(-1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-3', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), evidence=mappingproxy({'visibility_fraction': 0.0, 'occluding_objects': (WorldObject(name='Chair', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-1', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))),), 'sample_count': 9}))"
  },
  "branch": {
    "status": "PASS",
    "result": "<reality._branch.WorldBranch object at 0x00000190B531EF50>"
  },
  "move": {
    "status": "PASS",
    "result": "WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))"
  },
  "consequences": {
    "status": "PASS",
    "result": "ConsequenceSet(consequences=(Consequence(what_changed='distance', previous_value=1.0, new_value=1.5, magnitude=0.5, objects=(WorldObject(name='Chair', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-1', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='distance changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 1.0, 'new_measurement': 1.5})), Consequence(what_changed='near', previous_value=True, new_value=False, magnitude=0.5, objects=(WorldObject(name='Chair', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-1', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='near changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 1.0, 'new_measurement': 1.5})), Consequence(what_changed='distance', previous_value=3.0, new_value=3.5, magnitude=0.5, objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Viewer', local_bounds=Bounds(minimum=(-2.0, 0.0, 0.0), maximum=(-1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-3', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='distance changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 3.0, 'new_measurement': 3.5})), Consequence(what_changed='near.measurement', previous_value=3.0, new_value=3.5, magnitude=0.5, objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Viewer', local_bounds=Bounds(minimum=(-2.0, 0.0, 0.0), maximum=(-1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-3', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='near changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 3.0, 'new_measurement': 3.5})), Consequence(what_changed='distance', previous_value=2.23606797749979, new_value=2.5, magnitude=0.2639320225002102, objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Door', local_bounds=Bounds(minimum=(0.0, 3.0, 0.0), maximum=(1.0, 3.1, 2.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-4', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='distance changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 2.23606797749979, 'new_measurement': 2.5})), Consequence(what_changed='near.measurement', previous_value=2.23606797749979, new_value=2.5, magnitude=0.2639320225002102, objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Door', local_bounds=Bounds(minimum=(0.0, 3.0, 0.0), maximum=(1.0, 3.1, 2.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-4', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='near changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 2.23606797749979, 'new_measurement': 2.5})), Consequence(what_changed='distance', previous_value=4.123105625617661, new_value=4.272001872658765, magnitude=0.1488962470411046, objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Opening', local_bounds=Bounds(minimum=(0.0, 5.0, 0.0), maximum=(1.0, 5.1, 2.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-5', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='distance changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 4.123105625617661, 'new_measurement': 4.272001872658765})), Consequence(what_changed='near.measurement', previous_value=4.123105625617661, new_value=4.272001872658765, magnitude=0.1488962470411046, objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Opening', local_bounds=Bounds(minimum=(0.0, 5.0, 0.0), maximum=(1.0, 5.1, 2.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-5', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='near changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 4.123105625617661, 'new_measurement': 4.272001872658765})), Consequence(what_changed='distance', previous_value=2.9000000000000004, new_value=2.4000000000000004, magnitude=0.5, objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Exit', local_bounds=Bounds(minimum=(5.9, -0.1, 0.0), maximum=(6.1, 0.1, 0.2)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-6', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='distance changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 2.9000000000000004, 'new_measurement': 2.4000000000000004})), Consequence(what_changed='near.measurement', previous_value=2.9000000000000004, new_value=2.4000000000000004, magnitude=0.5, objects=(WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Exit', local_bounds=Bounds(minimum=(5.9, -0.1, 0.0), maximum=(6.1, 0.1, 0.2)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-6', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), classification='direct', reason='near changed within the branch dependency frontier.', evidence=mappingproxy({'previous_measurement': 2.9000000000000004, 'new_measurement': 2.4000000000000004}))), changes=ChangeSet(changes=(MoveObject(object_id='object-2', object_name='Table', old_state=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), new_state=Transform(position=(0.5, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), parameters=mappingproxy({'x': 0.5, 'y': 0.0, 'z': 0.0}), order=1, timestamp=datetime.datetime(2026, 9, 27, 8, 34, 50, 27649, tzinfo=datetime.timezone.utc)),)), instrumentation=GraphUpdateStats(predicates_before=211, invalidated=71, recalculated=71, reused=140))"
  },
  "agent": {
    "status": "PASS",
    "result": "Agent(id='agent-1', name='Person', position=(0.0, 0.0, 0.0), height=1.75, radius=0.3, step_height=0.0, max_slope=None)"
  },
  "can_reach": {
    "status": "PASS",
    "result": "ReachabilityResult(reachable=False, path=PathResult(reachable=False, points=(), distance=None, minimum_clearance=None, narrowest_point=None, blocked_by=(WorldObject(name='Chair', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-1', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), reason='No collision-free path; blocked by Chair, Table.', evidence=mappingproxy({'algorithm': 'A* (8-connected occupancy grid)', 'coordinate_system': 'XY ground plane, Z up', 'resolution': 0.25, 'grid_size': (41, 17), 'visited_cells': 1, 'required_clearance': 0.6, 'target_id': 'object-6', 'max_slope': None})), required_clearance=0.6, available_clearance=0.0, blocked_by=(WorldObject(name='Chair', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-1', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), reason='No collision-free path; blocked by Chair, Table.', evidence=mappingproxy({'agent_id': 'agent-1', 'path': PathResult(reachable=False, points=(), distance=None, minimum_clearance=None, narrowest_point=None, blocked_by=(WorldObject(name='Chair', local_bounds=Bounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-1', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))), WorldObject(name='Table', local_bounds=Bounds(minimum=(2.0, 0.0, 0.0), maximum=(3.0, 1.0, 1.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-2', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0)))), reason='No collision-free path; blocked by Chair, Table.', evidence=mappingproxy({'algorithm': 'A* (8-connected occupancy grid)', 'coordinate_system': 'XY ground plane, Z up', 'resolution': 0.25, 'grid_size': (41, 17), 'visited_cells': 1, 'required_clearance': 0.6, 'target_id': 'object-6', 'max_slope': None}))}))"
  },
  "can_pass": {
    "status": "PASS",
    "result": "PassageResult(can_pass=True, required_width=0.6, available_width=1.0, required_height=1.75, available_height=2.0, reason='Opening provides the required width and height.', objects=(WorldObject(name='Opening', local_bounds=Bounds(minimum=(0.0, 5.0, 0.0), maximum=(1.0, 5.1, 2.0)), transform=Transform(position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), id='object-5', physical=PhysicalProperties(mass=1.0, dynamic=False, collision_shape='box', friction=0.5, restitution=0.0, center_of_mass=(0.0, 0.0, 0.0))),), evidence=mappingproxy({'agent_id': 'agent-1', 'opening_bounds': Bounds(minimum=(0.0, 5.0, 0.0), maximum=(1.0, 5.1, 2.0))}))"
  },
  "can_rotate": {
    "status": "PASS",
    "result": "MotionResult(possible=True, requested=45.0, maximum_collision_free=45.0, collision_at=None, collides_with=(), units='deg', reason='The complete sampled motion path is collision-free.', samples_tested=45, evidence=mappingproxy({'method': 'sampled swept world-AABB', 'resolution': 1.0, 'joint_limits': (0.0, 90.0)}))"
  },
  "simulate": {
    "status": "PASS",
    "result": "SimulationResult(backend='mujoco-cpu', backend_version='3.14.0', seconds=0.05, time_step=0.004166666666666667, steps=12, bodies=(BodySimulationResult(object_id='object-1', object_name='Ball', initial_transform=Transform(position=(0.0, 0.0, 1.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), final_transform=Transform(position=(0.0, 0.0, 0.988759375), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)), initial_velocity=(0.0, 0.0, 0.0), final_velocity=(0.0, 0.0, -0.449625), contacts=(), fell=True, motion=0.011240625000000004),), deterministic=True, evidence=mappingproxy({'collision_approximation': 'world-axis-aligned boxes', 'ground_plane': 'z=0', 'integrator': 'MuJoCo fixed-step Euler'}))"
  }
}
```

## 4. Full Test Suite

- passed: `61`
- failed: `0`
- skipped: `0`
- xfailed: `0`
- runtime_seconds: `4.3042035000398755`
- returncode: `0`

```text
.............................................................            [100%]
61 passed in 1.11s

```

## 5. Lint and Type Check

- Ruff: `PASS` in 0.428s
- MyPy: `PASS` in 17.159s

```text
All checks passed!
Success: no issues found in 15 source files
```

## 6. CPU vs GPU Correctness

No Reality GPU operation is implemented or claimed. Comparison cases: 0; matching: 0;
failures: 0; maximum/mean error: not applicable. Warp 1.17.0 is installed, but
CUDA availability is `False` (CUDA driver/device is unavailable.). CPU reference behavior remains
available. This is an explicit validation gap, not a skipped success.

## 7. Branch Isolation

```json
{
  "base_position": [
    0.0,
    0.0,
    0.0
  ],
  "branch_a_position": [
    2.0,
    0.0,
    0.0
  ],
  "branch_b_position": [
    0.0,
    0.0,
    0.0
  ],
  "unchanged_object_shared": true,
  "mesh_shared_after_change": true,
  "status": "PASS"
}
```

## 8. Memory Efficiency

```json
{
  "objects": 200,
  "branches": 100,
  "method": "tracemalloc current allocated bytes while all alternatives remain live",
  "naive_deepcopy_bytes": 7273344,
  "reality_branch_bytes": 194752,
  "ratio_naive_to_reality": 37.34669733815314
}
```

## 9. Performance Benchmarks

Actual one-repetition cold CPU measurements from this audit run. GPU rows are absent because
CUDA is unavailable; no speedup is calculated.

```json
[
  {
    "backend": "cpu-numpy",
    "branches": 1,
    "end_to_end_seconds": 0.0038451000000350177,
    "evaluation_seconds": 0.0032963999547064304,
    "delta_bytes": 24,
    "repetitions": 1,
    "warmup": "none"
  },
  {
    "backend": "cpu-numpy",
    "branches": 10,
    "end_to_end_seconds": 0.0005490999901667237,
    "evaluation_seconds": 0.00010060000931844115,
    "delta_bytes": 240,
    "repetitions": 1,
    "warmup": "none"
  },
  {
    "backend": "cpu-numpy",
    "branches": 100,
    "end_to_end_seconds": 0.00023309997050091624,
    "evaluation_seconds": 6.059999577701092e-05,
    "delta_bytes": 2400,
    "repetitions": 1,
    "warmup": "none"
  },
  {
    "backend": "cpu-numpy",
    "branches": 1000,
    "end_to_end_seconds": 0.0003410999779589474,
    "evaluation_seconds": 0.00020059995586052537,
    "delta_bytes": 24000,
    "repetitions": 1,
    "warmup": "none"
  },
  {
    "backend": "cpu-numpy",
    "branches": 10000,
    "end_to_end_seconds": 0.0016617000219412148,
    "evaluation_seconds": 0.0010017000022344291,
    "delta_bytes": 240000,
    "repetitions": 1,
    "warmup": "none"
  }
]
```

## 10. Consequence Engine Demonstration

```json
{
  "before": true,
  "change": "Blocker y -= 3.0",
  "after": false,
  "detected": [
    {
      "what_changed": "distance",
      "previous_value": 2.80178514522438,
      "new_value": 1.6,
      "magnitude": 1.2017851452243797,
      "objects": [
        {
          "id": "object-1",
          "name": "Viewer"
        },
        {
          "id": "object-3",
          "name": "Blocker"
        }
      ],
      "classification": "direct",
      "reason": "distance changed within the branch dependency frontier.",
      "evidence": {
        "previous_measurement": 2.80178514522438,
        "new_measurement": 1.6
      }
    },
    {
      "what_changed": "near.measurement",
      "previous_value": 2.80178514522438,
      "new_value": 1.6,
      "magnitude": 1.2017851452243797,
      "objects": [
        {
          "id": "object-1",
          "name": "Viewer"
        },
        {
          "id": "object-3",
          "name": "Blocker"
        }
      ],
      "classification": "direct",
      "reason": "near changed within the branch dependency frontier.",
      "evidence": {
        "previous_measurement": 2.80178514522438,
        "new_measurement": 1.6
      }
    },
    {
      "what_changed": "distance",
      "previous_value": 2.920616373302046,
      "new_value": 1.7999999999999998,
      "magnitude": 1.1206163733020462,
      "objects": [
        {
          "id": "object-2",
          "name": "Target"
        },
        {
          "id": "object-3",
          "name": "Blocker"
        }
      ],
      "classification": "direct",
      "reason": "distance changed within the branch dependency frontier.",
      "evidence": {
        "previous_measurement": 2.920616373302046,
        "new_measurement": 1.7999999999999998
      }
    },
    {
      "what_changed": "near.measurement",
      "previous_value": 2.920616373302046,
      "new_value": 1.7999999999999998,
      "magnitude": 1.1206163733020462,
      "objects": [
        {
          "id": "object-2",
          "name": "Target"
        },
        {
          "id": "object-3",
          "name": "Blocker"
        }
      ],
      "classification": "direct",
      "reason": "near changed within the branch dependency frontier.",
      "evidence": {
        "previous_measurement": 2.920616373302046,
        "new_measurement": 1.7999999999999998
      }
    },
    {
      "what_changed": "visible_from",
      "previous_value": true,
      "new_value": false,
      "magnitude": 1.0,
      "objects": [
        {
          "id": "object-2",
          "name": "Target"
        },
        {
          "id": "object-1",
          "name": "Viewer"
        }
      ],
      "classification": "downstream",
      "reason": "Deterministic visibility changed after branch mutations.",
      "evidence": {
        "previous": {
          "value": true,
          "measurement": 3.8,
          "units": "m",
          "reason": "At least one deterministic target sample has unobstructed line of sight.",
          "objects": [
            {
              "id": "object-2",
              "name": "Target"
            },
            {
              "id": "object-1",
              "name": "Viewer"
            }
          ],
          "evidence": {
            "visibility_fraction": 1.0,
            "occluding_objects": [],
            "sample_count": 9
          }
        },
        "new": {
          "value": false,
          "measurement": 3.8,
          "units": "m",
          "reason": "Every deterministic target sample is blocked by scene geometry.",
          "objects": [
            {
              "id": "object-2",
              "name": "Target"
            },
            {
              "id": "object-1",
              "name": "Viewer"
            }
          ],
          "evidence": {
            "visibility_fraction": 0.0,
            "occluding_objects": [
              {
                "id": "object-3",
                "name": "Blocker"
              }
            ],
            "sample_count": 9
          }
        }
      }
    }
  ],
  "has_direct": true,
  "has_downstream": true
}
```

## 11. Navigation Demonstration

```json
{
  "before_reachable": true,
  "after_reachable": false,
  "blocking_objects": [
    "Shelf"
  ]
}
```

## 12. Articulation Demonstration

```json
{
  "requested": 90.0,
  "maximum_allowed": 27.46875,
  "blocking_objects": [
    "Plant"
  ],
  "reason": "Motion is blocked by Plant near 28 deg."
}
```

## 13. Physics Demonstration

```json
{
  "backend": "mujoco-cpu",
  "support_change": "x += 3.0",
  "initial_position": [
    0.0,
    0.0,
    0.0
  ],
  "final_position": [
    -1.4481685384622146e-35,
    -4.25317697854237e-19,
    -1.0107080100141865
  ],
  "fell": true,
  "contact_count": 4
}
```

## 14. Dependency Inventory

- **NumPy:** vector arithmetic and CPU batch arrays; not Reality-owned.
- **Trimesh:** GLB/glTF/OBJ parsing and opaque mesh objects; not Reality-owned.
- **MuJoCo:** rigid-body integration and contact generation for the CPU physics backend;
  not Reality-owned.
- **NVIDIA Warp:** installed only for capability probing on this host. No Reality Warp kernel
  is implemented or active.
- **pytest, Ruff, MyPy:** testing, lint/format checks, and static type checking.
- **OpenUSD:** not installed or used.

## 15. Original Reality Technology

- **Reality Graph — IMPLEMENTED:** `src/reality/_graph.py`; typed relationships, lazy query
  records, incident-edge invalidation, and reuse instrumentation.
- **Physical predicate abstraction — IMPLEMENTED:** `src/reality/_world.py` and
  `src/reality/_models.py`; deterministic backend-neutral AABB results and evidence.
- **Dependency tracking — IMPLEMENTED:** `src/reality/_graph.py`; spatial, visibility,
  navigation, and articulation query invalidation. Some global occluder/path dependencies
  conservatively invalidate all known queries.
- **Branch/delta representation — IMPLEMENTED:** `src/reality/_branch.py`; shared immutable
  snapshot and changed-object overlay.
- **Consequence engine — IMPLEMENTED:** `src/reality/_branch.py`; direct, downstream, and
  simulation-observed typed comparisons.
- **Branch comparison — IMPLEMENTED:** `World.compare` in `src/reality/_world.py`.
- **Batched branch evaluation — PARTIAL:** `src/reality/_batch.py`; compact translation
  deltas and CPU collision batches exist, but visibility/consequence batches and CUDA kernels
  do not.

## 16. Known Limitations

- Import supports GLB, glTF, and OBJ only; no arbitrary CAD or USD importer.
- Core geometry uses world AABBs, which are conservative for rotated/sparse meshes.
- Graph construction and incremental changed-object refresh remain O(n²) and O(n).
- Visibility samples one center and eight corners, not exact raster visibility.
- Navigation is a finite flat XY grid; slope and 3D locomotion are not evaluated.
- Articulation uses finite swept-AABB samples and explicit joint metadata only.
- Physics uses MuJoCo box colliders, a z=0 plane, and does not map rotational outcomes.
- Batched evaluation supports translation and collision only.
- Warp is installed but no CUDA driver/device is available; no GPU kernels were validated.
- This audit ran on one Windows/Python 3.11 host; other platforms remain unverified here.

## 17. Unsupported Claims

- “Reality supports arbitrary CAD or USD files.”
- “Reality infers articulation or semantic material properties automatically.”
- “Reality provides exact triangle-mesh predicates, visibility, or collision.”
- “Reality is a complete physics engine.”
- “Reality currently provides NVIDIA GPU acceleration.”
- “Reality has validated CPU/GPU numerical parity or a measured GPU speedup.”
- “All predicates, visibility, navigation, and consequences are batch-evaluated.”

## 18. Reproduction Commands

```bash
python -m pip install -e ".[dev,physics,gpu]"
python -m pytest -q
python -m ruff check .
python -m mypy src
python benchmarks/articulation.py
python benchmarks/physics_cpu.py
python benchmarks/batch_branches.py
python tools/reality_audit.py --full --output REALITY_AUDIT.md
```

GPU benchmarks have no runnable command beyond the audit probe because no GPU kernel is
implemented; inventing one would misrepresent the repository.

## 19. Final Machine-Generated Status

REALITY_STATUS=PARTIAL
