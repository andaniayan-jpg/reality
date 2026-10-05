"""Explicit feature routing and file-only media entry points."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import reality
from reality._core.router import Feature, ModelRouter
from reality._providers.base import AITask, AIUnavailableError, RetryableProviderError
from reality._providers.configured import online_router_from_env
from reality._providers.gemini import GeminiProvider
from reality._providers.ollama import OllamaProvider
from reality.layers import twin


class RecordingProvider:
    def __init__(self, *, failing: bool = False) -> None:
        self.calls: list[tuple[str, AITask]] = []
        self.failing = failing

    def complete(self, task: AITask, *, model: str) -> str:
        self.calls.append((model, task))
        if self.failing:
            raise RetryableProviderError("private provider detail")
        return "Unverified visual or physical guidance"


@pytest.mark.parametrize(
    ("feature", "expected"),
    [
        ("copilot", "qwen3:14b"),
        ("reason.predict", "qwen3:14b"),
        ("reason.forces", "qwen3:14b"),
        ("reason.cascade", "qwen3:14b"),
        ("simulate.world", "qwen3:14b"),
        ("simulate.stream", "phi4:mini"),
        ("generate.object", "deepseek-coder-v2"),
        ("generate.scene", "qwen3:14b"),
        ("twin.predict", "qwen3:14b"),
        ("twin.anomalies", "qwen3:14b"),
        ("agents.spawn", "qwen3:14b"),
        ("agents.train", "qwen3:14b"),
    ],
)
def test_explicit_text_feature_map(feature: Feature, expected: str) -> None:
    local = RecordingProvider()
    router = ModelRouter(
        {"local": local},
        local_models=("qwen3:14b", "phi4:mini", "deepseek-coder-v2:latest"),
    )
    assert router.route_feature(feature, AITask("task")).mode == "local"
    assert local.calls == [
        (expected if expected != "deepseek-coder-v2" else f"{expected}:latest", AITask("task"))
    ]


def test_public_copilot_uses_feature_route_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    reality.logout()
    monkeypatch.delenv("REALITY_API_KEY", raising=False)
    local = RecordingProvider()
    router = ModelRouter({"local": local}, local_models=("qwen3:14b", "phi4:mini"))
    monkeypatch.setattr("reality.layers.copilot._default_router", lambda: router)
    answer = reality.copilot("How would the object fall?")
    assert answer.mode == "local"
    assert local.calls[0][0] == "qwen3:14b"


def test_vision_prefers_configured_provider_and_falls_back_locally() -> None:
    vision = AITask("Describe", kind="vision", image=b"image")
    cloud = RecordingProvider()
    local = RecordingProvider()
    router = ModelRouter({"gemini": cloud, "local": local}, local_models=("qwen2-vl:7b",))
    assert router.route_feature("perceive.from_image", vision).mode == "online"
    assert cloud.calls[0][0] == "gemini-2.5-flash"
    assert not local.calls
    cloud.failing = True
    assert router.route_feature("capture.from_image", vision).mode == "local"
    assert local.calls[0][0] == "qwen2-vl:7b"


def test_vision_without_cloud_uses_installed_local_or_clear_failure() -> None:
    vision = AITask("Describe", kind="vision", image=b"image")
    local = RecordingProvider()
    fallback = ModelRouter({"local": local}, local_models=("llava:7b",))
    assert fallback.route_feature("twin.from_video", vision).mode == "local"
    assert fallback.route_feature("reason.forces", vision).mode == "local"
    assert local.calls[0][0] == "llava:7b"
    with pytest.raises(AIUnavailableError, match="Image analysis is unavailable"):
        ModelRouter({"local": local}).route_feature("perceive.from_image", vision)


def test_text_does_not_silently_swap_models_or_expose_provider_detail() -> None:
    local = RecordingProvider(failing=True)
    router = ModelRouter({"local": local}, local_models=("qwen3:14b", "phi4:mini"))
    with pytest.raises(AIUnavailableError, match="temporarily unavailable") as failure:
        router.route_feature("copilot", AITask("Question"))
    assert "private provider detail" not in str(failure.value)
    with pytest.raises(AIUnavailableError, match="required local AI engine"):
        ModelRouter({"local": local}, local_models=("phi4:mini",)).route_feature(
            "copilot", AITask("Question")
        )
    quick = ModelRouter({"local": RecordingProvider()}, local_models=("phi4:mini",))
    assert quick.route_feature("copilot", AITask("Question", realtime=True)).mode == "local"
    with pytest.raises(ValueError, match="unsupported AI feature"):
        router.route_feature("invented.feature", AITask("Question"))  # type: ignore[arg-type]


def test_capture_uses_image_file_and_never_exposes_camera(tmp_path: Path) -> None:
    image = tmp_path / "photo.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    local = RecordingProvider()
    router = ModelRouter({"local": local}, local_models=("qwen2-vl:7b",))
    observation = reality.reality.capture(source=image, router=router)
    assert isinstance(observation, reality.AIResponse)
    assert local.calls[0][1].kind == "vision"
    assert not hasattr(reality.perceive, "from_camera")


def test_environment_key_enables_file_vision_without_local_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "photo.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    reality.logout()
    monkeypatch.delenv("REALITY_API_KEY", raising=False)
    monkeypatch.delenv("REALITY_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def unavailable(self: OllamaProvider) -> tuple[str, ...]:
        raise AIUnavailableError("not running")

    monkeypatch.setattr(OllamaProvider, "available_models", unavailable)
    monkeypatch.setattr(GeminiProvider, "complete", lambda self, task, *, model: "image seen")
    assert reality.perceive.from_image(image).mode == "online"
    assert isinstance(online_router_from_env().providers["gemini"], GeminiProvider)


def test_video_accepts_only_bounded_mp4_and_returns_sampled_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "scan.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"data")
    local = RecordingProvider()
    router = ModelRouter({"local": local}, local_models=("qwen2-vl:7b",))

    def extracted(source: Path, destination: Path, limit: int) -> tuple[Path, ...]:
        assert source == video.resolve() and limit == 2
        frames = (destination / "frame-001.png", destination / "frame-002.png")
        for frame in frames:
            frame.write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return frames

    monkeypatch.setattr(twin, "_extract_frames", extracted)
    observations = reality.twin.from_video(video, max_frames=2, router=router)
    assert observations.sampled_frames == 2
    assert len(observations.frames) == 2
    assert all(frame.mode == "local" for frame in observations.frames)
    assert len(local.calls) == 2
    with pytest.raises(ValueError, match="max_frames"):
        reality.twin.from_video(video, max_frames=5, router=router)
    video.write_bytes(b"not an mp4 file")
    with pytest.raises(ValueError, match="MP4 format"):
        reality.twin.from_video(video, router=router)


def test_real_mp4_file_decoding_without_live_capture(tmp_path: Path) -> None:
    ffmpeg = pytest.importorskip("imageio_ffmpeg")
    video = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            ffmpeg.get_ffmpeg_exe(),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:d=2",
            "-c:v",
            "mpeg4",
            str(video),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    local = RecordingProvider()
    router = ModelRouter({"local": local}, local_models=("qwen2-vl:7b",))
    observations = reality.twin.from_video(video, max_frames=2, router=router)
    assert observations.sampled_frames == 2
    assert len(local.calls) == 2
