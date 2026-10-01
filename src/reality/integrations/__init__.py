"""Verified external-runtime integration contracts and adapters."""

from .base import (
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationError,
    IntegrationRegistry,
    IntegrationSyncResult,
    IntegrationUnavailableError,
    UnsupportedIntegrationCapabilityError,
    WorldIntegration,
)
from .manifest import SceneManifestError, SceneManifestIntegration
from .mujoco import MuJoCoSceneIntegration

__all__ = [
    "IntegrationCapability",
    "IntegrationDescriptor",
    "IntegrationError",
    "IntegrationRegistry",
    "IntegrationSyncResult",
    "IntegrationUnavailableError",
    "MuJoCoSceneIntegration",
    "SceneManifestError",
    "SceneManifestIntegration",
    "UnsupportedIntegrationCapabilityError",
    "WorldIntegration",
]
