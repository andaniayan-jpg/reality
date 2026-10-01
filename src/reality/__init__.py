"""Reality: a backend-neutral foundation for programmable 3D worlds."""

# Kept available for runtime diagnostics and wheel-install verification.
# The package metadata in ``pyproject.toml`` is the release source of truth.
__version__ = "0.2.0"

from ._accelerators import AccelerationUnavailableError, WarpStatus, warp_status
from ._agent import (
    AgentAction,
    AgentExecution,
    AgentPlan,
    AgentPlanError,
    AgentProvider,
    RealityAgent,
)
from ._articulation import (
    ArticulatedObject,
    Articulation,
    Joint,
    MotionResult,
    PrismaticJoint,
    RevoluteJoint,
)
from ._batch import (
    BatchEvaluation,
    BranchBatch,
    FutureCandidate,
    Futures,
    FutureSelection,
    RankedFutures,
)
from ._branch import WorldBranch
from ._editing import EditOperation, EditOperationError, EditResult, EditSession, EditValidation
from ._explore import ExplorationResult, PositionSearchChange, position
from ._file_model import (
    CADBackendUnavailableError,
    ModelAssembly,
    ModelFileError,
    ModelPart,
    ModelResult,
    ModelValidation,
    RealityModel,
    open_model,
)
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
from .integrations import (
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationError,
    IntegrationRegistry,
    IntegrationSyncResult,
    IntegrationUnavailableError,
    SceneManifestError,
    SceneManifestIntegration,
    UnsupportedIntegrationCapabilityError,
    WorldIntegration,
)
from .predicates import (
    Condition,
    Objective,
    PredicateSpec,
    collision,
    distance,
    maximize,
    minimize,
    no_collision,
    visibility,
)

__all__ = [
    "__version__",
    "AmbiguousObjectError",
    "AccelerationUnavailableError",
    "AgentAction",
    "AgentExecution",
    "AgentPlan",
    "AgentPlanError",
    "AgentProvider",
    "Agent",
    "ArticulatedObject",
    "Articulation",
    "Bounds",
    "BatchEvaluation",
    "BodySimulationResult",
    "BranchBatch",
    "Condition",
    "Change",
    "ChangeSet",
    "CADBackendUnavailableError",
    "Consequence",
    "ConsequenceSet",
    "Contact",
    "ClearanceResult",
    "GraphUpdateStats",
    "IntegrationCapability",
    "IntegrationDescriptor",
    "IntegrationError",
    "IntegrationRegistry",
    "IntegrationSyncResult",
    "IntegrationUnavailableError",
    "FutureCandidate",
    "FutureSelection",
    "Futures",
    "ExplorationResult",
    "EditOperation",
    "EditOperationError",
    "EditResult",
    "EditSession",
    "EditValidation",
    "Joint",
    "MoveObject",
    "MotionResult",
    "ModelAssembly",
    "ModelFileError",
    "ModelPart",
    "ModelResult",
    "ModelValidation",
    "NavigationGrid",
    "ObjectNotFoundError",
    "PhysicalProperties",
    "PositionSearchChange",
    "PhysicsBackendUnavailableError",
    "PredicateResult",
    "PrismaticJoint",
    "PassageResult",
    "PathResult",
    "RealityGraph",
    "RealityAgent",
    "RealityModel",
    "ReachabilityResult",
    "RankedFutures",
    "Relationship",
    "RelationshipType",
    "RevoluteJoint",
    "RotateObject",
    "ScaleObject",
    "SceneManifestError",
    "SceneManifestIntegration",
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
    "UnsupportedIntegrationCapabilityError",
    "WorldIntegration",
    "load",
    "Objective",
    "PredicateSpec",
    "collision",
    "distance",
    "maximize",
    "minimize",
    "no_collision",
    "open",
    "position",
    "visibility",
    "warp_status",
]

# ``open`` is intentionally a new model-oriented API. ``load`` retains the
# v0.1 World API for interactive spatial-world use.
open = open_model
