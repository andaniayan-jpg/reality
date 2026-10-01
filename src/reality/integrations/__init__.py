"""Verified external-runtime integration contracts and adapters."""

from .base import (
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationError,
    IntegrationRegistry,
    IntegrationStatus,
    IntegrationSyncResult,
    IntegrationUnavailableError,
    UnsupportedIntegrationCapabilityError,
    WorldIntegration,
)
from .blender import (
    BlenderSceneIntegration,
    BlenderTransformChange,
    BlenderTransformPreview,
    register_addon,
    unregister_addon,
)
from .manifest import SceneManifestError, SceneManifestIntegration
from .mujoco import (
    MuJoCoActuatorInfo,
    MuJoCoBodyState,
    MuJoCoJointInfo,
    MuJoCoRolloutResult,
    MuJoCoSceneInfo,
    MuJoCoSceneIntegration,
    MuJoCoSensorInfo,
)

__all__ = [
    "IntegrationCapability",
    "IntegrationDescriptor",
    "IntegrationError",
    "IntegrationRegistry",
    "IntegrationStatus",
    "IntegrationSyncResult",
    "IntegrationUnavailableError",
    "BlenderSceneIntegration",
    "BlenderTransformChange",
    "BlenderTransformPreview",
    "MuJoCoActuatorInfo",
    "MuJoCoBodyState",
    "MuJoCoJointInfo",
    "MuJoCoRolloutResult",
    "MuJoCoSceneInfo",
    "MuJoCoSceneIntegration",
    "MuJoCoSensorInfo",
    "SceneManifestError",
    "SceneManifestIntegration",
    "UnsupportedIntegrationCapabilityError",
    "WorldIntegration",
    "register_addon",
    "unregister_addon",
]
