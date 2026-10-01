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

__all__ = [
    "IntegrationCapability",
    "IntegrationDescriptor",
    "IntegrationError",
    "IntegrationRegistry",
    "IntegrationSyncResult",
    "IntegrationUnavailableError",
    "SceneManifestError",
    "SceneManifestIntegration",
    "UnsupportedIntegrationCapabilityError",
    "WorldIntegration",
]
