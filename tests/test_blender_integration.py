"""Tests that do not pretend Blender is installed when it is not."""

from __future__ import annotations

from pathlib import Path

import pytest

from reality import BlenderSceneIntegration, IntegrationUnavailableError


def test_blender_adapter_reports_unavailable_runtime_without_importing_bpy() -> None:
    adapter = BlenderSceneIntegration()
    status = adapter.status()

    assert status.descriptor.name == "blender-active-scene"
    if not status.available:
        assert "bpy" in status.reason
        with pytest.raises(IntegrationUnavailableError, match="active Blender scene"):
            adapter.import_world(Path(__file__))


def test_blender_descriptor_does_not_claim_file_import_or_live_sync() -> None:
    capabilities = BlenderSceneIntegration().descriptor.capabilities

    assert "import_scene" not in capabilities
    assert "export_scene" not in capabilities
    assert "live_sync" not in capabilities
