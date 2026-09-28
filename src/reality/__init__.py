"""Reality: a backend-neutral foundation for programmable 3D worlds."""

from ._accelerators import AccelerationUnavailableError, WarpStatus, warp_status
from ._articulation import (
    ArticulatedObject,
    Articulation,
    Joint,
    MotionResult,
    PrismaticJoint,
    RevoluteJoint,
)
from ._batch import BatchEvaluation, BranchBatch
from ._branch import WorldBranch
from ._graph import GraphUpdateStats, RealityGraph, Relationship, RelationshipType
from ._loaders import load
from ._metadata import SceneMetadataError
from ._models import Bounds, PhysicalProperties, PredicateResult, Transform, WorldObject
from ._navigation import (
    Agent,
    ClearanceResult,
    NavigationGrid,
    PassageResult,
    PathResult,
    ReachabilityResult,
)
from ._physics import (
    BodySimulationResult,
    Contact,
    PhysicsBackendUnavailableError,
    SimulationResult,
    StabilityResult,
    UnsupportedPhysicsOperationError,
)
from ._state import (
    Change,
    ChangeSet,
    Consequence,
    ConsequenceSet,
    MoveObject,
    RotateObject,
    ScaleObject,
    WorldSnapshot,
)
from ._world import AmbiguousObjectError, ObjectNotFoundError, World

__all__ = [
    "AmbiguousObjectError",
    "AccelerationUnavailableError",
    "Agent",
    "ArticulatedObject",
    "Articulation",
    "Bounds",
    "BatchEvaluation",
    "BodySimulationResult",
    "BranchBatch",
    "Change",
    "ChangeSet",
    "Consequence",
    "ConsequenceSet",
    "Contact",
    "ClearanceResult",
    "GraphUpdateStats",
    "Joint",
    "MoveObject",
    "MotionResult",
    "NavigationGrid",
    "ObjectNotFoundError",
    "PhysicalProperties",
    "PhysicsBackendUnavailableError",
    "PredicateResult",
    "PrismaticJoint",
    "PassageResult",
    "PathResult",
    "RealityGraph",
    "ReachabilityResult",
    "Relationship",
    "RelationshipType",
    "RevoluteJoint",
    "RotateObject",
    "ScaleObject",
    "SceneMetadataError",
    "SimulationResult",
    "StabilityResult",
    "Transform",
    "World",
    "WorldBranch",
    "WorldObject",
    "WorldSnapshot",
    "WarpStatus",
    "UnsupportedPhysicsOperationError",
    "load",
    "warp_status",
]
