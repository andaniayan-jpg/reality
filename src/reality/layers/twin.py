"""Bounded, file-only video observations. No live camera or inferred 3D twin."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from reality._core.router import ModelRouter
from reality._providers.base import AIResponse

from .perceive import from_image

MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_FRAMES = 4


@dataclass(frozen=True, slots=True)
class VideoObservations:
    """Descriptions of sampled frames, not a geometric or predictive digital twin."""

    source: Path
    frames: tuple[AIResponse, ...]
    sampled_frames: int


def _extract_frames(source: Path, destination: Path, limit: int) -> tuple[Path, ...]:
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError("Video support requires `pip install reality[video]`") from error
    try:
        executable = imageio_ffmpeg.get_ffmpeg_exe()
        completed = subprocess.run(
            [
                executable,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-vf",
                "fps=1,scale=768:768:force_original_aspect_ratio=decrease",
                "-frames:v",
                str(limit),
                str(destination / "frame-%03d.png"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Video decoding failed or timed out") from error
    if completed.returncode != 0:
        raise ValueError("Video could not be decoded")
    frames = tuple(sorted(destination.glob("frame-*.png")))
    if not frames:
        raise ValueError("Video contained no decodable frames")
    return frames


def from_video(
    path: str | Path,
    *,
    prompt: str = "Describe only visible objects and changes in this frame; state uncertainty.",
    max_frames: int = MAX_FRAMES,
    router: ModelRouter | None = None,
) -> VideoObservations:
    """Analyze up to four sampled frames from a user-supplied MP4 file.

    The original video is not uploaded; each extracted frame follows the
    configured image-perception route, which may use a cloud vision service.
    """
    source = Path(path).resolve(strict=True)
    if source.suffix.lower() != ".mp4":
        raise ValueError("only MP4 video files are supported")
    size = source.stat().st_size
    if size < 12 or size > MAX_VIDEO_BYTES:
        raise ValueError("video must be between 12 bytes and 100 MiB")
    with source.open("rb") as stream:
        if stream.read(12)[4:8] != b"ftyp":
            raise ValueError("video content does not match MP4 format")
    if not 1 <= max_frames <= MAX_FRAMES:
        raise ValueError("max_frames must be between 1 and 4")
    with TemporaryDirectory(prefix="reality-video-") as temporary:
        frames = _extract_frames(source, Path(temporary), max_frames)
        observations = tuple(from_image(frame, prompt=prompt, router=router) for frame in frames)
    return VideoObservations(source, observations, len(observations))
