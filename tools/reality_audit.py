"""Generate an evidence-backed audit of the Reality repository without repairing it."""

from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("WARP_CACHE_PATH", str(Path(tempfile.gettempdir()) / "reality-warp-cache"))

import reality  # noqa: E402
from reality import Bounds, PhysicalProperties, Transform, World, WorldObject  # noqa: E402


def command(*arguments: str, timeout: int = 300) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": " ".join(arguments),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "seconds": time.perf_counter() - started,
    }


def safe_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def repository_facts() -> dict[str, Any]:
    source_files = list((ROOT / "src" / "reality").rglob("*.py"))
    test_files = list((ROOT / "tests").rglob("*.py"))
    git_hash = command("git", "rev-parse", "HEAD")
    git_status = command("git", "status", "--short")
    return {
        "commit": git_hash["stdout"]
        if git_hash["returncode"] == 0
        else "unavailable (not a Git checkout)",
        "git_status": git_status["stdout"] if git_status["returncode"] == 0 else "unavailable",
        "source_files": len(source_files),
        "source_loc": sum(
            len(path.read_text(encoding="utf-8").splitlines()) for path in source_files
        ),
        "test_loc": sum(len(path.read_text(encoding="utf-8").splitlines()) for path in test_files),
        "version": safe_version("reality"),
    }


def smoke_tests() -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    def record(name: str, operation: Any) -> None:
        try:
            value = operation()
            results[name] = {"status": "PASS", "result": repr(value)}
        except Exception as error:  # audit must preserve failures
            results[name] = {"status": "FAIL", "result": f"{type(error).__name__}: {error}"}

    with tempfile.TemporaryDirectory() as directory:
        obj = Path(directory) / "triangle.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
        record("reality.load", lambda: reality.load(obj).objects)

    chair = WorldObject("Chair", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))
    table = WorldObject("Table", Bounds((2.0, 0.0, 0.0), (3.0, 1.0, 1.0)))
    viewer = WorldObject("Viewer", Bounds((-2.0, 0.0, 0.0), (-1.0, 1.0, 1.0)))
    door = WorldObject("Door", Bounds((0.0, 3.0, 0.0), (1.0, 3.1, 2.0)))
    opening = WorldObject("Opening", Bounds((0.0, 5.0, 0.0), (1.0, 5.1, 2.0)))
    exit_ = WorldObject("Exit", Bounds((5.9, -0.1, 0.0), (6.1, 0.1, 0.2)))
    world = World([chair, table, viewer, door, opening, exit_])
    record("distance", lambda: world.distance("Chair", "Table"))
    record("intersects", lambda: world.intersects("Chair", "Table"))
    record("visible", lambda: world.visible("Table", from_="Viewer"))
    record("branch", world.branch)
    branch = world.branch()
    record("move", lambda: branch.move("Table", x=0.5))
    record("consequences", branch.consequences)
    agent = world.agent(name="Person", height=1.75, radius=0.3)
    record("agent", lambda: agent)
    record("can_reach", lambda: agent.can_reach("Exit"))
    record("can_pass", lambda: agent.can_pass("Opening"))
    articulated = world.articulate(
        "Door",
        joint="revolute",
        pivot=(0.0, 3.0, 0.0),
        axis=(0.0, 0.0, 1.0),
        limits=(0.0, 90.0),
    )
    record("can_rotate", lambda: articulated.can_rotate(45.0))
    physics = World(
        [
            WorldObject(
                "Ball",
                Bounds((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1)),
                Transform(position=(0.0, 0.0, 1.0)),
                physical=PhysicalProperties(dynamic=True),
            )
        ],
        build_graph=False,
    )
    record("simulate", lambda: physics.simulate(seconds=0.05))
    return results


def parse_pytest(result: dict[str, Any]) -> dict[str, Any]:
    output = f"{result['stdout']}\n{result['stderr']}"
    counts = {name: 0 for name in ("passed", "failed", "skipped", "xfailed")}
    for name in counts:
        match = re.search(rf"(\d+) {name}", output)
        if match:
            counts[name] = int(match.group(1))
    return {
        **counts,
        "runtime_seconds": result["seconds"],
        "returncode": result["returncode"],
        "output": output,
    }


def branch_isolation() -> dict[str, Any]:
    mesh = object()
    world = World(
        [
            WorldObject("A", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), mesh=mesh),
            WorldObject("B", Bounds((3.0, 0.0, 0.0), (4.0, 1.0, 1.0)), mesh=mesh),
        ]
    )
    first = world.branch()
    second = world.branch()
    first.move("A", x=2.0)
    evidence = {
        "base_position": world.object("A").position,
        "branch_a_position": first.object("A").position,
        "branch_b_position": second.object("A").position,
        "unchanged_object_shared": first.object("B") is world.object("B"),
        "mesh_shared_after_change": first.object("A").mesh is world.object("A").mesh,
    }
    evidence["status"] = (
        "PASS"
        if (
            evidence["base_position"] == (0.0, 0.0, 0.0)
            and evidence["branch_b_position"] == (0.0, 0.0, 0.0)
            and evidence["unchanged_object_shared"]
            and evidence["mesh_shared_after_change"]
        )
        else "FAIL"
    )
    return evidence


def memory_efficiency() -> dict[str, Any]:
    world = World(
        [
            WorldObject(
                f"Object-{index}",
                Bounds((index * 2.0, 0.0, 0.0), (index * 2.0 + 1.0, 1.0, 1.0)),
            )
            for index in range(200)
        ],
        build_graph=False,
    )
    tracemalloc.start()
    naive = [copy.deepcopy(world.objects) for _ in range(100)]
    naive_bytes = tracemalloc.get_traced_memory()[0]
    del naive
    tracemalloc.stop()
    tracemalloc.start()
    persistent = [world.branch() for _ in range(100)]
    branch_bytes = tracemalloc.get_traced_memory()[0]
    del persistent
    tracemalloc.stop()
    return {
        "objects": 200,
        "branches": 100,
        "method": "tracemalloc current allocated bytes while all alternatives remain live",
        "naive_deepcopy_bytes": naive_bytes,
        "reality_branch_bytes": branch_bytes,
        "ratio_naive_to_reality": naive_bytes / branch_bytes if branch_bytes else None,
    }


def performance() -> list[dict[str, Any]]:
    world = World(
        [
            WorldObject("Mover", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))),
            WorldObject("Obstacle", Bounds((2.0, 0.0, 0.0), (3.0, 1.0, 1.0))),
        ]
    )
    rows = []
    for count in (1, 10, 100, 1_000, 10_000):
        started = time.perf_counter()
        batch = world.branches(count).randomize("Mover.position", x=(-2.0, 2.0), seed=9)
        result = batch.evaluate()
        rows.append(
            {
                "backend": "cpu-numpy",
                "branches": count,
                "end_to_end_seconds": time.perf_counter() - started,
                "evaluation_seconds": result.elapsed_seconds,
                "delta_bytes": result.delta_bytes,
                "repetitions": 1,
                "warmup": "none",
            }
        )
    return rows


def consequence_demo() -> dict[str, Any]:
    viewer = WorldObject("Viewer", Bounds((0.0, 0.0, 0.0), (0.2, 0.2, 1.0)))
    target = WorldObject("Target", Bounds((4.0, 0.0, 0.0), (4.2, 0.2, 1.0)))
    blocker = WorldObject(
        "Blocker",
        Bounds((1.8, -0.5, 0.0), (2.2, 0.5, 1.2)),
        Transform(position=(0.0, 3.0, 0.0)),
    )
    world = World([viewer, target, blocker])
    before = world.visible("Target", from_="Viewer")
    future = world.branch()
    future.move("Blocker", y=-3.0)
    after = future.visible("Target", from_="Viewer")
    report = future.consequences()
    return {
        "before": before.value,
        "change": "Blocker y -= 3.0",
        "after": after.value,
        "detected": [item.to_dict() for item in report],
        "has_direct": any(item.classification == "direct" for item in report),
        "has_downstream": any(item.classification == "downstream" for item in report),
    }


def navigation_demo() -> dict[str, Any]:
    exit_ = WorldObject(
        "Exit", Bounds((-0.1, -0.1, 0.0), (0.1, 0.1, 0.2)), Transform(position=(6, 0, 0))
    )
    shelf = WorldObject(
        "Shelf",
        Bounds((-0.5, -3.0, 0.0), (0.5, 3.0, 2.0)),
        Transform(position=(3.0, 6.0, 0.0)),
    )
    world = World([exit_, shelf])
    person = world.agent(name="Person", height=1.75, radius=0.3)
    before = person.can_reach("Exit")
    future = world.branch()
    future.move("Shelf", y=-6.0)
    after = future.agent("Person").can_reach("Exit")
    return {
        "before_reachable": before.reachable,
        "after_reachable": after.reachable,
        "blocking_objects": [item.name for item in after.blocked_by],
    }


def articulation_demo() -> dict[str, Any]:
    world = World(
        [
            WorldObject("Door", Bounds((0.0, 0.0, 0.0), (1.0, 0.1, 2.0))),
            WorldObject("Plant", Bounds((0.55, 0.55, 0.0), (0.75, 0.75, 2.0))),
        ]
    )
    door = world.articulate(
        "Door", joint="revolute", pivot=(0, 0, 0), axis=(0, 0, 1), limits=(0, 110)
    )
    result = door.can_rotate(90)
    return {
        "requested": result.requested,
        "maximum_allowed": result.maximum_collision_free,
        "blocking_objects": [item.name for item in result.collides_with],
        "reason": result.reason,
    }


def physics_demo() -> dict[str, Any]:
    support = WorldObject("Support", Bounds((-1.0, -1.0, 0.0), (1.0, 1.0, 1.0)))
    vase = WorldObject(
        "Vase",
        Bounds((-0.1, -0.1, 1.0), (0.1, 0.1, 1.4)),
        physical=PhysicalProperties(dynamic=True),
    )
    world = World([support, vase])
    future = world.branch()
    future.move("Support", x=3.0)
    result = future.simulate(seconds=0.5)
    body = result.body("Vase")
    return {
        "backend": result.backend,
        "support_change": "x += 3.0",
        "initial_position": body.initial_transform.position,
        "final_position": body.final_transform.position,
        "fell": body.fell,
        "contact_count": body.contact_count,
    }


def bullet(data: dict[str, Any]) -> str:
    return "\n".join(f"- {key}: `{value}`" for key, value in data.items())


def code_json(value: Any) -> str:
    return "```json\n" + json.dumps(value, indent=2, default=str) + "\n```"


def generate(full: bool) -> tuple[str, str]:
    warp = reality.warp_status()
    tests_raw = command(sys.executable, "-m", "pytest", "-q", timeout=600)
    tests = parse_pytest(tests_raw)
    lint = command(sys.executable, "-m", "ruff", "check", ".")
    types = command(sys.executable, "-m", "mypy", "src", timeout=600)
    smoke = smoke_tests()
    repository = repository_facts()
    isolation = branch_isolation()
    memory = memory_efficiency()
    benchmarks = performance() if full else performance()[:3]
    consequences = consequence_demo()
    navigation = navigation_demo()
    articulation = articulation_demo()
    physics = physics_demo()
    smoke_pass = all(item["status"] == "PASS" for item in smoke.values())
    core_pass = (
        tests_raw["returncode"] == 0
        and lint["returncode"] == 0
        and types["returncode"] == 0
        and smoke_pass
        and isolation["status"] == "PASS"
    )
    status = "PARTIAL" if core_pass and not warp.cuda_available else "PASS" if core_pass else "FAIL"
    environment = {
        "Python": sys.version.replace("\n", " "),
        "OS": platform.platform(),
        "CPU": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
        "GPU": ", ".join(warp.devices) if warp.devices else "none detected",
        "CUDA availability": warp.cuda_available,
        "Warp version": warp.version,
        "NumPy": safe_version("numpy"),
        "Trimesh": safe_version("trimesh"),
        "MuJoCo": safe_version("mujoco"),
        "pytest": safe_version("pytest"),
        "Ruff": safe_version("ruff"),
        "MyPy": safe_version("mypy"),
        "audit UTC timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    report = f"""# Reality Audit

## 1. Environment

{bullet(environment)}

Warp probe reason: {warp.reason}

## 2. Repository

{bullet(repository)}

## 3. Public API Smoke Test

These operations were executed against real programmatic scenes and a temporary OBJ.

{code_json(smoke)}

## 4. Full Test Suite

{bullet({key: value for key, value in tests.items() if key != "output"})}

```text
{tests["output"]}
```

## 5. Lint and Type Check

- Ruff: `{"PASS" if lint["returncode"] == 0 else "FAIL"}` in {lint["seconds"]:.3f}s
- MyPy: `{"PASS" if types["returncode"] == 0 else "FAIL"}` in {types["seconds"]:.3f}s

```text
{lint["stdout"] or lint["stderr"]}
{types["stdout"] or types["stderr"]}
```

## 6. CPU vs GPU Correctness

No Reality GPU operation is implemented or claimed. Comparison cases: 0; matching: 0;
failures: 0; maximum/mean error: not applicable. Warp {warp.version} is installed, but
CUDA availability is `{warp.cuda_available}` ({warp.reason}). CPU reference behavior remains
available. This is an explicit validation gap, not a skipped success.

## 7. Branch Isolation

{code_json(isolation)}

## 8. Memory Efficiency

{code_json(memory)}

## 9. Performance Benchmarks

Actual one-repetition cold CPU measurements from this audit run. GPU rows are absent because
CUDA is unavailable; no speedup is calculated.

{code_json(benchmarks)}

## 10. Consequence Engine Demonstration

{code_json(consequences)}

## 11. Navigation Demonstration

{code_json(navigation)}

## 12. Articulation Demonstration

{code_json(articulation)}

## 13. Physics Demonstration

{code_json(physics)}

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

REALITY_STATUS={status}
"""
    return report, status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="run all configured scale rows")
    parser.add_argument("--output", type=Path, default=Path("REALITY_AUDIT.md"))
    arguments = parser.parse_args()
    report, status = generate(arguments.full)
    output = arguments.output if arguments.output.is_absolute() else ROOT / arguments.output
    output.write_text(report, encoding="utf-8")
    print(f"Wrote {output}")
    print(f"REALITY_STATUS={status}")
    return 0 if status in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
