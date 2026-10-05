"""Reality: a backend-neutral foundation for programmable 3D worlds."""

# Kept available for runtime diagnostics and wheel-install verification.
# The package metadata in ``pyproject.toml`` is the release source of truth.
__version__ = "0.2.1"

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
from ._blender_conversion import BlenderConversionRequired
from ._branch import WorldBranch
from ._bridge import BridgeRequestError, RealityBridge, serve_jsonl
from ._core.auth import detect_mode, login, logout
from ._core.detector import HardwareProfile, detect_hardware
from ._core.installer import LocalSetupPlan, local_setup_plan
from ._core.router import ModelRouter
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
from ._ledger_store import JsonlLedgerStore, LedgerIntegrityError, LedgerVerification
from ._loaders import load
from ._materials import MaterialProperties, material
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
from ._physics_object import PhysicsObject, WeakPoint
from ._provenance import ProvenanceEntry, WorldLedger, WorldProvenance, provenance_for
from ._providers.base import (
    AIResponse,
    AITask,
    AIUnavailableError,
    Provider,
    RetryableProviderError,
)
from ._robot_model import DeclaredJoint
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
    BlenderSceneIntegration,
    BlenderTransformChange,
    BlenderTransformPreview,
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationError,
    IntegrationRegistry,
    IntegrationStatus,
    IntegrationSyncResult,
    IntegrationUnavailableError,
    MuJoCoActuatorInfo,
    MuJoCoBodyState,
    MuJoCoJointInfo,
    MuJoCoRolloutResult,
    MuJoCoSceneInfo,
    MuJoCoSceneIntegration,
    MuJoCoSensorInfo,
    SceneManifestError,
    SceneManifestIntegration,
    UnsupportedIntegrationCapabilityError,
    WorldIntegration,
    register_addon,
    unregister_addon,
)
from .layers import perceive, reason, twin
from .layers import reality_capture as reality
from .layers.copilot import copilot
from .layers.twin import VideoObservations
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
    "AIResponse",
    "AITask",
    "AIUnavailableError",
    "HardwareProfile",
    "LocalSetupPlan",
    "ModelRouter",
    "Provider",
    "RetryableProviderError",
    "copilot",
    "detect_hardware",
    "detect_mode",
    "local_setup_plan",
    "login",
    "logout",
    "perceive",
    "reason",
    "reality",
    "twin",
    "VideoObservations",
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
    "BlenderSceneIntegration",
    "BlenderConversionRequired",
    "BlenderTransformChange",
    "BlenderTransformPreview",
    "BridgeRequestError",
    "BatchEvaluation",
    "BodySimulationResult",
    "BranchBatch",
    "Condition",
    "Change",
    "ChangeSet",
    "CADBackendUnavailableError",
    "Consequence",
    "ConsequenceSet",
    "DeclaredJoint",
    "Contact",
    "ClearanceResult",
    "GraphUpdateStats",
    "IntegrationCapability",
    "IntegrationDescriptor",
    "IntegrationError",
    "IntegrationRegistry",
    "IntegrationStatus",
    "IntegrationSyncResult",
    "IntegrationUnavailableError",
    "MuJoCoActuatorInfo",
    "MuJoCoBodyState",
    "MuJoCoJointInfo",
    "MuJoCoRolloutResult",
    "MuJoCoSceneInfo",
    "MuJoCoSceneIntegration",
    "MuJoCoSensorInfo",
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
    "JsonlLedgerStore",
    "LedgerIntegrityError",
    "LedgerVerification",
    "MoveObject",
    "MotionResult",
    "ModelAssembly",
    "ModelFileError",
    "ModelPart",
    "ModelResult",
    "ModelValidation",
    "MaterialProperties",
    "NavigationGrid",
    "ObjectNotFoundError",
    "PhysicalProperties",
    "PhysicsObject",
    "PositionSearchChange",
    "ProvenanceEntry",
    "PhysicsBackendUnavailableError",
    "PredicateResult",
    "PrismaticJoint",
    "PassageResult",
    "PathResult",
    "RealityGraph",
    "RealityAgent",
    "RealityBridge",
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
    "WorldLedger",
    "WorldProvenance",
    "WorldBranch",
    "WorldObject",
    "WorldSnapshot",
    "WeakPoint",
    "WarpStatus",
    "UnsupportedPhysicsOperationError",
    "UnsupportedIntegrationCapabilityError",
    "WorldIntegration",
    "load",
    "material",
    "Objective",
    "PredicateSpec",
    "collision",
    "distance",
    "maximize",
    "minimize",
    "no_collision",
    "open",
    "position",
    "provenance_for",
    "visibility",
    "warp_status",
    "register_addon",
    "serve_jsonl",
    "unregister_addon",
]

# ``open`` is intentionally a new model-oriented API. ``load`` retains the
# v0.1 World API for interactive spatial-world use.
open = open_model
