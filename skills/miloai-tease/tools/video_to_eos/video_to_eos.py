from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import imageio_ffmpeg
from PIL import Image


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_numeric_id(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:12], 16)


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def link_or_copy(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"Hash destination collision: {destination}")
        return
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a video to a timed EOS image-sequence WebTease."
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--title", default="24 FPS Video Playback Test")
    parser.add_argument("--author", default="Local Author")
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional maximum conversion duration in seconds.",
    )
    parser.add_argument(
        "--resume-incomplete",
        action="store_true",
        help="Reuse an existing incomplete project directory only when it has no media.",
    )
    parser.add_argument(
        "--reuse-media-from",
        type=Path,
        default=None,
        help="Reuse frame_*.jpg and an MP3 from another media directory.",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=2,
        help="FFmpeg JPEG qscale (2 is high quality; range 2-31).",
    )
    parser.add_argument(
        "--frames-per-page",
        type=int,
        default=24,
        help=(
            "Number of sequential frames per EOS page. The runtime preloads an "
            "entire page, so short pages allow streaming playback."
        ),
    )
    return parser.parse_args()


def ensure_inputs(args: argparse.Namespace) -> tuple[Path, Path]:
    video = args.video.resolve()
    projects_root = args.projects_root.resolve()
    project_dir = (projects_root / args.project_id).resolve()

    if not video.is_file():
        raise SystemExit(f"Video does not exist: {video}")
    if args.fps <= 0:
        raise SystemExit("--fps must be greater than zero")
    if args.duration is not None and args.duration <= 0:
        raise SystemExit("--duration must be greater than zero")
    if not 2 <= args.jpeg_quality <= 31:
        raise SystemExit("--jpeg-quality must be between 2 and 31")
    if args.frames_per_page <= 0:
        raise SystemExit("--frames-per-page must be greater than zero")
    if project_dir.parent != projects_root:
        raise SystemExit("--project-id must be a single safe directory name")
    if not args.project_id.isdigit():
        raise SystemExit(
            "--project-id must contain digits only because the bundled EOS Editor "
            "converts tease IDs with Number(teaseId)"
        )
    if project_dir.exists():
        media_files = project_dir / "media" / "files"
        has_media = media_files.exists() and any(media_files.iterdir())
        has_deliverable = (
            (project_dir / "project.json").exists()
            or (project_dir / "eosscript.json").exists()
        )
        if not args.resume_incomplete or has_media or has_deliverable:
            raise SystemExit(
                f"Project already exists and will not be overwritten: {project_dir}"
            )
    return video, project_dir


def convert_media(
    ffmpeg: str,
    video: Path,
    media_dir: Path,
    fps: float,
    jpeg_quality: int,
    duration: float | None,
) -> None:
    frame_pattern = media_dir / "frame_%06d.jpg"
    audio_path = media_dir / "video_audio.mp3"
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-i",
        str(video),
    ]
    if duration is not None:
        command.extend(["-t", f"{duration:g}"])
    command.extend([
        "-map",
        "0:v:0",
        "-vf",
        f"fps={fps:g}",
        "-q:v",
        str(jpeg_quality),
        "-start_number",
        "1",
        str(frame_pattern),
        "-map",
        "0:a:0?",
        "-vn",
    ])
    if duration is not None:
        command.extend(["-t", f"{duration:g}"])
    command.extend([
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(audio_path),
    ])
    print("Running:", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True)


def package_media(
    project_dir: Path,
    frames: list[Path],
    audio_path: Path | None,
) -> tuple[dict[str, dict], dict[str, dict], str, str | None]:
    image_dir = project_dir / "media" / "timg" / "tb_xl"
    audio_dir = project_dir / "media" / "timg"
    image_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict] = {}
    gallery_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"miloai-editor:{project_dir.name}:video-frames",
        )
    )
    gallery_images: list[dict] = []

    with Image.open(frames[0]) as image:
        width, height = image.size

    for frame in frames:
        digest = sha1_file(frame)
        link_or_copy(frame, image_dir / f"{digest}.jpg")
        gallery_images.append({
            "id": stable_numeric_id(frame.name),
            "hash": digest,
            "size": frame.stat().st_size,
            "width": width,
            "height": height,
        })

    audio_name = None
    if audio_path and audio_path.is_file():
        audio_name = audio_path.name
        digest = sha1_file(audio_path)
        link_or_copy(audio_path, audio_dir / f"{digest}.mp3")
        files[audio_name] = {
            "id": stable_numeric_id(audio_name),
            "hash": digest,
            "size": audio_path.stat().st_size,
            "type": "audio/mpeg",
        }
    galleries = {
        gallery_id: {
            "name": "Video Frames",
            "images": gallery_images,
        }
    }
    return files, galleries, gallery_id, audio_name


def build_eos(
    project_dir: Path,
    video: Path,
    fps: float,
    frames: list[Path],
    audio_path: Path | None,
    frames_per_page: int = 24,
) -> tuple[dict, int]:
    if not frames:
        raise RuntimeError("No frame images were supplied")

    files, galleries, gallery_id, audio_name = package_media(
        project_dir,
        frames,
        audio_path,
    )
    frame_locator = lambda frame: (
        f"gallery:{gallery_id}/{stable_numeric_id(frame.name)}"
    )
    first_playback_page = "playback_000001"
    pages: dict[str, list[dict]] = {
        "start": [
            {"image": {"locator": frame_locator(frames[0])}},
            {
                "say": {
                    "label": (
                        f"<p><strong>{fps:g} FPS EOS image-sequence test</strong></p>"
                        f"<p>{len(frames):,} frames. Click Start to begin.</p>"
                    ),
                    "mode": "instant",
                }
            },
            {
                "choice": {
                    "options": [
                        {
                            "label": "Start",
                            "commands": [
                                {"goto": {"target": first_playback_page}}
                            ],
                        }
                    ]
                }
            },
        ],
        "finished": [
            {
                "say": {
                    "label": "<p><strong>24 FPS playback test finished.</strong></p>",
                    "mode": "instant",
                }
            },
            {"end": {}},
        ],
    }

    for chunk_start in range(0, len(frames), frames_per_page):
        page_number = chunk_start // frames_per_page + 1
        page_name = f"playback_{page_number:06d}"
        chunk = frames[chunk_start:chunk_start + frames_per_page]
        playback: list[dict] = []
        if chunk_start == 0 and audio_name:
            playback.append(
                {
                    "audio.play": {
                        "locator": f"file:{audio_name}",
                        "volume": 1,
                        "loops": 1,
                        "background": True,
                        "id": "video_audio",
                    }
                }
            )
        for chunk_index, frame in enumerate(chunk):
            frame_index = chunk_start + chunk_index + 1
            playback.append({"image": {"locator": frame_locator(frame)}})
            # EOS parses literal durations as integer milliseconds. This
            # repeating pattern averages 41.666... ms, exactly 24 FPS.
            duration_ms = 41 if frame_index % 3 == 0 else 42
            timer: dict = {
                "duration": f"{duration_ms}ms",
                "style": "hidden",
            }
            if chunk_index == len(chunk) - 1:
                if frame_index == len(frames):
                    target = "finished"
                else:
                    target = f"playback_{page_number + 1:06d}"
                timer["commands"] = [{"goto": {"target": target}}]
            playback.append({"timer": timer})
        pages[page_name] = playback

    script = {
        "pages": pages,
        "files": files,
        "modules": {"audio": {}} if audio_name else {},
        "galleries": galleries,
        "init": (
            f"/* Generated from {video.name}; "
            f"{fps:g} FPS image-sequence playback test. */"
        ),
        "info": {
            "title": "EOS image-sequence playback test",
            "type": "EOS",
            "pages": len(pages),
            "files": len(files),
            "galleries": len(galleries),
            "images": len(frames),
        },
    }
    return script, len(frames)


def write_project(
    project_dir: Path,
    title: str,
    author: str,
    script: dict,
    source: Path,
    fps: float,
    frame_count: int,
    duration: float | None,
    frames_per_page: int,
) -> None:
    now = utc_now()
    metadata = {
        "id": project_dir.name,
        "title": title,
        "author": author,
        "createdAt": now,
        "updatedAt": now,
        "status": "draft",
    }
    manifest = {
        "source": str(source),
        "fps": fps,
        "frameCount": frame_count,
        "frameDurationMs": 1000 / fps,
        "framesPerPage": frames_per_page,
        "audio": next(
            (
                name
                for name, metadata in script.get("files", {}).items()
                if metadata.get("type") == "audio/mpeg"
            ),
            None,
        ),
        "framePattern": "frame_%06d.jpg",
        "requestedDurationSeconds": duration,
        "generatedAt": now,
    }
    (project_dir / "project.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (project_dir / "eosscript.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (project_dir / "video-sequence.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    video, project_dir = ensure_inputs(args)
    media_dir = project_dir / "media" / "files"
    for relative in (
        "history",
        "media/files",
        "media/timg/tb_xl",
        "media/archive",
        "storage",
        "ai/builds",
        "ai/issues",
        "ai/jobs",
        "ai/omp/sessions",
        "ai/revisions",
    ):
        (project_dir / relative).mkdir(parents=True, exist_ok=True)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        if args.reuse_media_from:
            reuse_dir = args.reuse_media_from.resolve()
            frames = sorted(reuse_dir.glob("frame_*.jpg"))
            audio_path = reuse_dir / "video_audio_5min.mp3"
            if not audio_path.is_file():
                audio_path = reuse_dir / "video_audio.mp3"
        else:
            convert_media(
                ffmpeg,
                video,
                media_dir,
                args.fps,
                args.jpeg_quality,
                args.duration,
            )
            frames = sorted(media_dir.glob("frame_*.jpg"))
            audio_path = media_dir / "video_audio.mp3"
        script, frame_count = build_eos(
            project_dir,
            video,
            args.fps,
            frames,
            audio_path if audio_path.is_file() else None,
            args.frames_per_page,
        )
        write_project(
            project_dir,
            args.title,
            args.author,
            script,
            video,
            args.fps,
            frame_count,
            args.duration,
            args.frames_per_page,
        )
    except Exception:
        print(
            "Conversion did not finish. Partial files were preserved; "
            "delete the incomplete project manually before retrying.",
            file=sys.stderr,
        )
        raise

    print(
        f"Created project {project_dir.name}: {frame_count} frames at "
        f"{args.fps:g} FPS",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
