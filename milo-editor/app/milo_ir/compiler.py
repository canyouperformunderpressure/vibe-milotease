from __future__ import annotations

import copy
import fnmatch
import hashlib
import io
import json
import mimetypes
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

from PIL import Image

from .models import (
    Action,
    BuildProduct,
    MaterializedAsset,
    MiloSourceError,
    SourceBundle,
    SourceIssue,
    RuntimeDocument,
    AssetDefinition,
)


_EOS_DURATION_DECIMAL_RE = re.compile(r"\d+\.\d+(?=(?:ms|w|d|h|m|s)(?:$|[-\d]))")


def _normalize_eos_duration(value: Any) -> Any:
    """Normalize decimal duration tokens to Milovana's canonical syntax.

    Milovana rejects decimal components with trailing zeroes (for example
    ``6.0s``) even though Milo accepts them. Keep expressions/unknown values
    untouched and only canonicalize literal duration tokens.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return f"{value:g}s"
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        normalized = token.rstrip("0").rstrip(".")
        return normalized or "0"

    return _EOS_DURATION_DECIMAL_RE.sub(replace, value)


def _normalize_all_eos_durations(value: Any) -> Any:
    """Recursively canonicalize duration fields in the final EOS document.

    This is a final safety net for raw EOS and deeply nested commands. It keeps
    Milo's permissive source syntax while guaranteeing that emitted duration
    fields satisfy Milovana's stricter decimal format.
    """
    if isinstance(value, list):
        return [_normalize_all_eos_durations(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"duration", "timerDuration"}:
            normalized[key] = _normalize_eos_duration(item)
        else:
            normalized[key] = _normalize_all_eos_durations(item)
    return normalized


def _normalize_nested_eos_command(command: Any) -> Any:
    """Canonicalize Milo shorthand that appears inside raw EOS command lists."""
    if not isinstance(command, dict) or len(command) != 1:
        return command
    kind, payload = next(iter(command.items()))

    if kind == "say":
        if isinstance(payload, str):
            payload = {"label": payload}
        elif isinstance(payload, dict) and isinstance(payload.get("duration"), str):
            payload["duration"] = _normalize_eos_duration(payload["duration"])
    elif kind == "goto" and isinstance(payload, str):
        payload = {"target": payload}
    elif kind in {"enable", "disable"} and isinstance(payload, str):
        payload = {"target": payload}
    elif kind == "timer" and isinstance(payload, str):
        payload = {"duration": _normalize_eos_duration(payload)}
    elif kind == "end" and isinstance(payload, bool):
        payload = {}

    if isinstance(payload, dict):
        if kind == "if":
            for field in ("commands", "elseCommands"):
                if isinstance(payload.get(field), list):
                    payload[field] = [_normalize_nested_eos_command(item) for item in payload[field]]
        elif kind == "choice" and isinstance(payload.get("options"), list):
            for option in payload["options"]:
                if isinstance(option, dict) and isinstance(option.get("commands"), list):
                    option["commands"] = [_normalize_nested_eos_command(item) for item in option["commands"]]
        elif kind == "timer" and isinstance(payload.get("commands"), list):
            payload["commands"] = [_normalize_nested_eos_command(item) for item in payload["commands"]]
            if isinstance(payload.get("duration"), str):
                payload["duration"] = _normalize_eos_duration(payload["duration"])
        elif kind == "notification.create":
            for field in ("buttonCommands", "timerCommands"):
                if isinstance(payload.get(field), list):
                    payload[field] = [_normalize_nested_eos_command(item) for item in payload[field]]
            if isinstance(payload.get("timerDuration"), str):
                payload["timerDuration"] = _normalize_eos_duration(payload["timerDuration"])
        elif kind == "noop" and isinstance(payload, dict):
            payload = _normalize_nested_eos_command(payload)

    return {kind: payload}
from .parser import load_project_sources
from .validator import (
    condition_to_js,
    normalize_asset_reference,
    normalize_choices,
    normalize_if,
    normalize_random,
    normalize_target,
    parse_condition,
    parse_set,
    set_to_js,
    validate_bundle,
    _is_raw_action,
)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
KNOWN_EOS_COMMANDS = {
    "say",
    "image",
    "audio.play",

    "timer",
    "goto",
    "choice",
    "if",
    "eval",
    "prompt",
    "notification.create",
    "notification.remove",
    "enable",
    "disable",
    "end",
    "noop",
    "storage",
}

PRELOAD_PAGE_ID = "--milo-preload-all"
PRELOAD_MAX_BATCHES = 50
PRELOAD_SMALL_CATALOG = 20
PRELOAD_HELPER_JS = r'''
var __milo_preload_notice_id = null;
var __milo_preload_target = null;
var __milo_preload_total = 0;
var __milo_preload_template = "Loading {percent}%  {bar}";
var __milo_preload_bar_width = 10;

function __miloPreloadReplaceAll(text, token, value) {
  return String(text).split(token).join(String(value));
}

function __miloPreloadBar(percent, width) {
  var filled = Math.floor((percent / 100) * width);
  if (filled < 0) filled = 0;
  if (filled > width) filled = width;
  var text = "";
  var i;
  for (i = 0; i < width; i++) text += i < filled ? "█" : "░";
  return text;
}

function __miloPreloadTitle(loaded, percent) {
  if (loaded < 0) loaded = 0;
  if (loaded > __milo_preload_total) loaded = __milo_preload_total;
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  var title = __milo_preload_template;
  title = __miloPreloadReplaceAll(title, "{percent}", percent);
  title = __miloPreloadReplaceAll(title, "{loaded}", loaded);
  title = __miloPreloadReplaceAll(title, "{total}", __milo_preload_total);
  title = __miloPreloadReplaceAll(title, "{bar}", __miloPreloadBar(percent, __milo_preload_bar_width));
  return title;
}

function __miloPreloadAdvance(loaded, percent) {
  var notice = Notification.get(__milo_preload_notice_id);
  if (notice) notice.setTitle(__miloPreloadTitle(Number(loaded) || 0, Number(percent) || 0));
}

function __miloPreloadStart(noticeId, target, total, sizeBytes, template, barWidth) {
  __milo_preload_notice_id = noticeId;
  __milo_preload_target = target;
  __milo_preload_total = Number(total) || 0;
  __milo_preload_template = template || "Loading {percent}%  {bar}";
  __milo_preload_bar_width = Number(barWidth) || 10;
  __miloPreloadAdvance(0, 0);
}

function __miloPreloadComplete() {
  __miloPreloadAdvance(__milo_preload_total, 100);
  var notice = Notification.get(__milo_preload_notice_id);
  if (notice) notice.remove();
  pages.goto(__milo_preload_target);
}
'''.strip()


def _problem(code: str, message: str, path: str = "") -> MiloSourceError:
    return MiloSourceError([SourceIssue("error", code, message, path)])


def _numeric_id(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF


def _resolve_source(project_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (project_dir / candidate).resolve()
        if candidate != project_dir and project_dir not in candidate.parents:
            raise _problem(
                "ASSET_SOURCE_OUTSIDE_PROJECT",
                "Relative asset paths cannot escape the project directory; external assets must use an explicit absolute path.",
                raw_path,
            )
        return candidate
    return candidate.resolve()


def _matches(relative: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    normalized = relative.replace("\\", "/")
    name = Path(normalized).name
    if include and not any(fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(name, pattern) for pattern in include):
        return False
    if exclude and any(fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(name, pattern) for pattern in exclude):
        return False
    return True


def _asset_files(project_dir: Path, asset: Any) -> list[tuple[Path, str]]:
    raw_source = asset.source or asset.folder or asset.file
    if raw_source is None:
        return []
    source = _resolve_source(project_dir, raw_source)
    if not source.exists():
        raise _problem("ASSET_SOURCE_MISSING", f"Asset source does not exist: {source}", f"milo.yaml.assets.{asset.asset_id}")
    source_is_folder = bool(asset.folder) or bool(asset.source and source.is_dir())
    if source_is_folder:
        if not source.is_dir():
            raise _problem("ASSET_FOLDER", f"folder is not a directory: {source}", f"milo.yaml.assets.{asset.asset_id}.folder")
        iterator = source.rglob("*") if asset.recursive else source.iterdir()
        files = [(path, path.relative_to(source).as_posix()) for path in iterator if path.is_file()]
    else:
        if not source.is_file():
            raise _problem("ASSET_FILE", f"file is not a file: {source}", f"milo.yaml.assets.{asset.asset_id}.file")
        files = [(source, source.name)]
    return sorted(
        [(path, relative) for path, relative in files if _matches(relative, asset.include, asset.exclude)],
        key=lambda item: item[1].casefold(),
    )


def _write_content_addressed(destination: Path, content: bytes) -> bool:
    if destination.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        # Preserve failed temporary output for diagnosis; no file is deleted automatically.
        raise
    return True


def _jpeg_bytes(path: Path) -> tuple[bytes, int, int]:
    try:
        with Image.open(path) as source:
            source.seek(0)
            image = source.convert("RGB")
            width, height = image.size
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=92, optimize=False, progressive=False)
            return output.getvalue(), width, height
    except (OSError, ValueError) as exc:
        raise _problem("ASSET_IMAGE_INVALID", f"Could not read image: {path}", str(path)) from exc


def _register_name(mapping: dict[str, Any], ambiguous: set[str], relative: str, value: Any) -> None:
    normalized = relative.replace("\\", "/")
    mapping[normalized] = value
    basename = Path(normalized).name
    existing = mapping.get(basename)
    if existing is None:
        mapping[basename] = value
    elif existing != value:
        ambiguous.add(basename)
        mapping.pop(basename, None)


def materialize_assets(project_dir: Path, bundle: SourceBundle) -> tuple[dict[str, MaterializedAsset], dict[str, Any], dict[str, Any], tuple[str, ...]]:
    project_dir = project_dir.resolve()
    materialized: dict[str, MaterializedAsset] = {}
    files: dict[str, Any] = {}
    galleries: dict[str, Any] = {}
    output_paths: list[str] = []
    used_image_ids: dict[str, set[int]] = defaultdict(set)

    for asset_id, asset in bundle.runtime.assets.items():
        result = MaterializedAsset(asset_id=asset_id, direct_locator=asset.locator)
        materialized[asset_id] = result
        if asset.locator:
            continue
        source_files = _asset_files(project_dir, asset)
        for source_path, relative in source_files:
            suffix = source_path.suffix.casefold()
            if suffix in IMAGE_SUFFIXES and asset.media_type != "audio":
                content, width, height = _jpeg_bytes(source_path)
                digest = hashlib.sha1(content).hexdigest()
                destination = project_dir / "media" / "timg" / "tb_xl" / f"{digest}.jpg"
                _write_content_addressed(destination, content)
                project_path = destination.relative_to(project_dir).as_posix()
                output_paths.append(project_path)
                image_id = _numeric_id(f"{asset_id}:{relative}")
                while image_id in used_image_ids[asset_id]:
                    image_id = (image_id + 1) & 0x7FFFFFFF
                used_image_ids[asset_id].add(image_id)
                record = {
                    "id": image_id,
                    "hash": digest,
                    "size": len(content),
                    "width": width,
                    "height": height,
                }
                result.images.append(record)
                _register_name(result.image_names, result.ambiguous_image_names, relative, image_id)
                continue
            if suffix in AUDIO_SUFFIXES and asset.media_type != "image":
                content = source_path.read_bytes()
                digest = hashlib.sha1(content).hexdigest()
                extension = suffix or mimetypes.guess_extension(mimetypes.guess_type(source_path.name)[0] or "") or ".bin"
                destination = project_dir / "media" / "files" / f"{digest}{extension}"
                _write_content_addressed(destination, content)
                project_path = destination.relative_to(project_dir).as_posix()
                output_paths.append(project_path)
                file_name = f"{asset_id}/{relative.replace('\\', '/')}"
                mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
                files[file_name] = {
                    "id": _numeric_id(f"{asset_id}:{relative}"),
                    "hash": digest,
                    "size": len(content),
                    "type": mime_type,
                }
                result.audio.append({"name": file_name, "hash": digest, "path": project_path})
                _register_name(result.audio_names, result.ambiguous_audio_names, relative, file_name)
        if result.images:
            result.gallery_id = f"milo-asset-{asset_id}"
            galleries[result.gallery_id] = {"name": asset_id, "images": result.images}
        if not result.images and not result.audio:
            raise _problem("ASSET_EMPTY", "The asset contains no usable image or audio files.", f"milo.yaml.assets.{asset_id}")
    return materialized, files, galleries, tuple(sorted(set(output_paths)))


def _prepare_inline_assets(bundle: SourceBundle, project_dir: Path) -> tuple[SourceBundle, dict[str, str]]:
    assets = dict(bundle.runtime.assets)
    references: dict[str, str] = {}
    raw_files = bundle.runtime.eos.get("files") if isinstance(bundle.runtime.eos.get("files"), dict) else {}
    raw_galleries = bundle.runtime.eos.get("galleries") if isinstance(bundle.runtime.eos.get("galleries"), dict) else {}
    gallery_names = {
        value.get("name") for value in raw_galleries.values()
        if isinstance(value, dict) and isinstance(value.get("name"), str)
    }
    for scene in bundle.scenes.values():
        for page in scene.pages.values():
            for action in page.actions:
                if action.kind not in {"image", "audio"} or _is_raw_action(action):
                    continue
                value = action.value
                reference = (value.get("asset") or value.get("file")) if isinstance(value, dict) else value
                if not isinstance(reference, str) or not reference.strip():
                    continue
                normalized = reference.strip().replace("\\", "/")
                if normalized.startswith(("file:", "gallery:")):
                    continue
                first = normalized.partition("/")[0]
                if first in assets or normalized in raw_files or normalized in raw_galleries or normalized in gallery_names:
                    continue
                candidate = _resolve_source(project_dir, reference)
                if not candidate.exists():
                    continue
                inline_id = "inline_" + hashlib.sha1(str(candidate).encode("utf-8")).hexdigest()[:16]
                assets.setdefault(
                    inline_id,
                    AssetDefinition(asset_id=inline_id, source=reference, media_type="image" if action.kind == "image" else "audio"),
                )
                references[normalized] = inline_id
    if assets == bundle.runtime.assets:
        return bundle, references
    runtime = replace(bundle.runtime, assets=assets)
    return replace(bundle, runtime=runtime), references


def _merge_catalog(base: dict[str, Any], generated: dict[str, Any], kind: str) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in generated.items():
        if key in result and result[key] != value:
            raise _problem("EOS_CATALOG_COLLISION", f"{kind} catalog name collision: {key}", f"milo.yaml.{kind}.{key}")
        result[key] = value
    return result


class _Compiler:
    def __init__(
        self,
        bundle: SourceBundle,
        assets: dict[str, MaterializedAsset],
        files: dict[str, Any],
        galleries: dict[str, Any],
        inline_references: dict[str, str],
    ):
        self.bundle = bundle
        self.assets = assets
        self.files = files
        self.galleries = galleries
        self.inline_references = inline_references
        self.asset_offsets: dict[str, int] = defaultdict(int)
        self.random_index = 0
        self.needs_audio = False
        self.needs_notification = False
        self.needs_state = False
        self.needs_preload = False
        self._preload_cache: tuple[list[dict[str, Any]], dict[str, int]] | None = None
        self._preload_command_sizes: list[int] = []

    def preload_catalog(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        if self._preload_cache is not None:
            return self._preload_cache
        commands: list[dict[str, Any]] = []
        seen: set[tuple[str, Any]] = set()
        total_bytes = 0
        image_count = 0
        audio_count = 0

        for gallery_id in sorted(self.galleries):
            gallery = self.galleries[gallery_id]
            images = gallery.get("images", []) if isinstance(gallery, dict) else []
            for image in images:
                if not isinstance(image, dict) or image.get("id") is None:
                    continue
                locator = f"gallery:{gallery_id}/{image['id']}"
                identity = ("image", image.get("hash") or locator)
                if identity in seen:
                    continue
                seen.add(identity)
                commands.append({"image": {"locator": locator}})
                image_size = int(image.get("size") or 0)
                self._preload_command_sizes.append(image_size)
                total_bytes += image_size
                image_count += 1

        for name in sorted(self.files):
            record = self.files[name]
            if not isinstance(record, dict):
                continue
            mime_type = str(record.get("type") or "")
            # The bundled EOS audio.play module resolves every locator as
            # audio/mpeg. Non-MP3 records therefore resolve to undefined and
            # crash the runtime preloader while reading `.hash`. Keep the
            # generic preload feature limited to the runtime-compatible MIME.
            if mime_type != "audio/mpeg":
                continue
            locator = f"file:{name}"
            identity = ("audio", record.get("hash") or locator)
            if identity in seen:
                continue
            seen.add(identity)
            commands.append({"audio.play": {"locator": locator, "volume": 0, "loops": 1}})
            audio_size = int(record.get("size") or 0)
            self._preload_command_sizes.append(audio_size)
            total_bytes += audio_size
            audio_count += 1

        stats = {
            "bytes": total_bytes,
            "images": image_count,
            "audio": audio_count,
            "total": image_count + audio_count,
        }
        self._preload_cache = (commands, stats)
        return self._preload_cache

    def preload_batches(self) -> list[tuple[list[dict[str, Any]], list[int]]]:
        commands, stats = self.preload_catalog()
        if not commands:
            return []
        sizes = self._preload_command_sizes
        if len(commands) <= PRELOAD_SMALL_CATALOG:
            return [(commands, sizes)]

        target_count = max(1, (len(commands) + PRELOAD_MAX_BATCHES - 1) // PRELOAD_MAX_BATCHES)
        target_bytes = (stats["bytes"] + PRELOAD_MAX_BATCHES - 1) // PRELOAD_MAX_BATCHES if stats["bytes"] else 0
        batches: list[tuple[list[dict[str, Any]], list[int]]] = []
        batch_commands: list[dict[str, Any]] = []
        batch_sizes: list[int] = []
        batch_bytes = 0

        for command, size in zip(commands, sizes):
            batch_commands.append(command)
            batch_sizes.append(size)
            batch_bytes += size
            count_ready = len(batch_commands) >= target_count
            bytes_ready = target_bytes > 0 and batch_bytes >= target_bytes
            if count_ready or bytes_ready:
                batches.append((batch_commands, batch_sizes))
                batch_commands = []
                batch_sizes = []
                batch_bytes = 0

        if batch_commands:
            batches.append((batch_commands, batch_sizes))
        return batches

    @staticmethod
    def preload_size_label(total_bytes: int) -> str:
        if total_bytes >= 1_000_000_000:
            return f"{total_bytes / 1_000_000_000:.1f} GB"
        if total_bytes >= 1_000_000:
            return f"{total_bytes / 1_000_000:.0f} MB"
        if total_bytes >= 1_000:
            return f"{total_bytes / 1_000:.0f} KB"
        return f"{total_bytes} B"

    @staticmethod
    def render_preload_text(template: str, stats: dict[str, int], percent: int = 0, bar_width: int = 10) -> str:
        bar_width = max(1, min(40, int(bar_width)))
        filled = max(0, min(bar_width, int((percent / 100) * bar_width)))
        replacements = {
            "{size}": _Compiler.preload_size_label(stats["bytes"]),
            "{bytes}": str(stats["bytes"]),
            "{images}": str(stats["images"]),
            "{audio}": str(stats["audio"]),
            "{total}": str(stats["total"]),
            "{loaded}": str(int((percent / 100) * stats["total"])),
            "{percent}": str(percent),
            "{bar}": "█" * filled + "░" * (bar_width - filled),
        }
        text = template
        for token, replacement in replacements.items():
            text = text.replace(token, replacement)
        return text

    def page_id(self, scene_id: str, local_page: str) -> str:
        return local_page

    def target(self, scene_id: str, raw_target: Any, path: str) -> str:
        target = normalize_target(raw_target, path)
        if target.startswith("$"):
            external = target[1:]
            scene = self.bundle.scenes[external]
            return scene.entry
        return target

    def _catalog_file(self, reference: str, path: str) -> str | None:
        if reference in self.files:
            return reference
        matches = [name for name in self.files if Path(name.replace("\\", "/")).name == reference]
        if len(matches) > 1:
            raise _problem("ASSET_NAME_AMBIGUOUS", f"The filename matches multiple catalog entries: {reference}", path)
        return matches[0] if matches else None

    def _catalog_gallery(self, reference: str, path: str) -> str | None:
        matches = [gallery_id for gallery_id, gallery in self.galleries.items() if gallery_id == reference or (isinstance(gallery, dict) and gallery.get("name") == reference)]
        unique = list(dict.fromkeys(matches))
        if len(unique) > 1:
            raise _problem("ASSET_NAME_AMBIGUOUS", f"The name matches multiple galleries: {reference}", path)
        return unique[0] if unique else None

    def _asset_reference(self, reference: Any, path: str) -> tuple[str | None, str | None, str | None]:
        if not isinstance(reference, str) or not reference.strip():
            raise _problem("ASSET_REFERENCE", "Media references must be non-empty strings.", path)
        normalized = reference.strip().replace("\\", "/")
        if normalized.startswith(("file:", "gallery:")):
            return None, None, normalized
        if normalized in self.assets:
            return normalized, None, None
        first, separator, selector = normalized.partition("/")
        if first in self.assets:
            return first, selector if separator else None, None
        file_name = self._catalog_file(normalized, path)
        if file_name is not None:
            return None, None, f"file:{file_name}"
        gallery_id = self._catalog_gallery(normalized, path)
        if gallery_id is not None:
            return None, None, f"gallery:{gallery_id}/*"
        inline_id = self.inline_references.get(normalized)
        if inline_id is not None:
            return inline_id, None, None
        return None, normalized, None

    def image_locator(self, value: Any, path: str) -> str:
        if isinstance(value, dict) and value.get("locator"):
            return value["locator"]
        reference = (value.get("asset") or value.get("file")) if isinstance(value, dict) else value
        asset_id, selector, direct = self._asset_reference(reference, path)
        if direct:
            return direct
        if isinstance(value, dict):
            selector = value.get("file") or value.get("pick") or selector
        if asset_id is None:
            matches: list[tuple[str, int]] = []
            for candidate_id, candidate in self.assets.items():
                if selector in candidate.ambiguous_image_names:
                    continue
                image_id = candidate.image_names.get(str(selector))
                if image_id is not None:
                    matches.append((candidate_id, image_id))
            if len(matches) != 1:
                code = "ASSET_IMAGE_NAME" if not matches else "ASSET_NAME_AMBIGUOUS"
                raise _problem(code, f"Image name cannot be resolved uniquely: {selector}", path)
            candidate_id, image_id = matches[0]
            gallery_id = self.assets[candidate_id].gallery_id
            return f"gallery:{gallery_id}/{image_id}"
        definition = self.bundle.runtime.assets[asset_id]
        materialized = self.assets[asset_id]
        if materialized.direct_locator:
            return materialized.direct_locator
        if not materialized.images or not materialized.gallery_id:
            raise _problem("ASSET_NOT_IMAGE", f"Asset contains no images: {asset_id}", path)
        selection = selector or definition.pick
        if selection == "random":
            return f"gallery:{materialized.gallery_id}/*"
        if selection in {"next", "sequence"}:
            index = self.asset_offsets[asset_id] % len(materialized.images)
            self.asset_offsets[asset_id] += 1
            image_id = materialized.images[index]["id"]
        elif selection == "first":
            image_id = materialized.images[0]["id"]
        else:
            image_id = materialized.image_names.get(str(selection).replace("\\", "/"))
            if image_id is None:
                raise _problem("ASSET_IMAGE_NAME", f"Asset {asset_id} does not contain image: {selection}", path)
        return f"gallery:{materialized.gallery_id}/{image_id}"

    def audio_locator(self, value: Any, path: str) -> str:
        if isinstance(value, dict) and value.get("locator"):
            return value["locator"]
        reference = value.get("asset") if isinstance(value, dict) else value
        asset_id, selector, direct = self._asset_reference(reference, path)
        if direct:
            if not direct.startswith("file:"):
                raise _problem("ASSET_NOT_AUDIO", "Audio references must resolve to a file locator.", path)
            return direct
        if asset_id is None:
            matches: list[str] = []
            for candidate in self.assets.values():
                if selector in candidate.ambiguous_audio_names:
                    continue
                name = candidate.audio_names.get(str(selector))
                if name is not None:
                    matches.append(name)
            unique = list(dict.fromkeys(matches))
            if len(unique) != 1:
                code = "ASSET_AUDIO_NAME" if not unique else "ASSET_NAME_AMBIGUOUS"
                raise _problem(code, f"Audio name cannot be resolved uniquely: {selector}", path)
            return f"file:{unique[0]}"
        materialized = self.assets[asset_id]
        if materialized.direct_locator:
            return materialized.direct_locator
        if not materialized.audio:
            raise _problem("ASSET_NOT_AUDIO", f"Asset contains no audio: {asset_id}", path)
        if selector and selector not in {"next", "sequence", "first", "random"}:
            name = materialized.audio_names.get(selector.replace("\\", "/"))
            if name is None:
                raise _problem("ASSET_AUDIO_NAME", f"Asset {asset_id} does not contain audio: {selector}", path)
        else:
            index = self.asset_offsets[asset_id] % len(materialized.audio)
            self.asset_offsets[asset_id] += 1
            name = materialized.audio[index]["name"]
        return f"file:{name}"

    def compile_action(self, scene_id: str, action: Action) -> list[dict[str, Any]]:
        value = action.value
        path = action.path
        if _is_raw_action(action):
            payload = copy.deepcopy(value)
            if (
                action.kind in {"say", "timer"}
                and isinstance(payload, dict)
                and isinstance(payload.get("duration"), str)
            ):
                payload["duration"] = _normalize_eos_duration(payload["duration"])
            if (
                action.kind == "notification.create"
                and isinstance(payload, dict)
                and isinstance(payload.get("timerDuration"), str)
            ):
                payload["timerDuration"] = _normalize_eos_duration(payload["timerDuration"])
            return [_normalize_nested_eos_command({action.kind: payload})]
        if action.kind == "say":
            if isinstance(value, str):
                payload = {"label": value}
            else:
                payload = copy.deepcopy(value)
                payload["label"] = payload.pop("text")
                if "duration" in payload:
                    payload["duration"] = _normalize_eos_duration(payload["duration"])
            return [{"say": payload}]
        if action.kind == "image":
            payload = copy.deepcopy(value) if isinstance(value, dict) else {}
            for field in ("asset", "pick", "file"):
                payload.pop(field, None)
            payload["locator"] = self.image_locator(value, path)
            return [{"image": payload}]
        if action.kind == "audio":
            data = value if isinstance(value, dict) else {}
            operation = data.get("action", "play")
            self.needs_audio = True
            if operation == "stop":
                sound_id = data.get("id")
                if not isinstance(sound_id, str) or not sound_id.strip():
                    raise _problem("AUDIO_STOP_ID", "audio.action=stop requires a non-empty id for Sound.get(id).stop().", path)
                encoded_id = json.dumps(sound_id.strip(), ensure_ascii=False)
                return [{"eval": {"script": f"var sound = Sound.get({encoded_id});\nif (sound) sound.stop();"}}]
            locator = self.audio_locator(value, path)
            payload = copy.deepcopy(data)
            payload.pop("asset", None)
            payload.pop("action", None)
            payload["locator"] = locator
            payload.setdefault("loops", 1)
            payload.setdefault("volume", 1)
            return [{"audio.play": payload}]
        if action.kind in {"wait", "timer"}:
            duration = value.get("duration") if isinstance(value, dict) else value
            normalized = _normalize_eos_duration(duration)
            payload = copy.deepcopy(value) if isinstance(value, dict) else {}
            payload["duration"] = normalized
            return [{"timer": payload}]
        if action.kind == "goto":
            return [{"goto": {"target": self.target(scene_id, value, path)}}]
        if action.kind in {"enable", "disable"}:
            return [{action.kind: {"target": normalize_target(value, path)}}]
        if action.kind == "choice":
            options = []
            for item in normalize_choices(value, path):
                option = copy.deepcopy(item["payload"])
                target_command = {"goto": {"target": self.target(scene_id, item["target"], path)}}
                existing_commands = option.get("commands")
                if existing_commands is None:
                    option["commands"] = [target_command]
                elif isinstance(existing_commands, list):
                    option["commands"] = [
                        *[_normalize_nested_eos_command(command) for command in existing_commands],
                        target_command,
                    ]
                else:
                    raise _problem("CHOICE_COMMANDS", "choice option commands must be a list.", path)
                options.append(option)
            return [{"choice": {"options": options}}]
        if action.kind == "if":
            self.needs_state = True
            branches, fallback = normalize_if(value, path)
            commands: list[dict[str, Any]] = []
            conditions: list[str] = []
            for raw_condition, target in branches:
                condition = condition_to_js(parse_condition(raw_condition, path))
                conditions.append(condition)
                commands.append({"if": {"condition": condition, "commands": [{"goto": {"target": self.target(scene_id, target, path)}}]}})
            if fallback:
                else_condition = "!(" + " || ".join(conditions) + ")"
                commands.append({"if": {"condition": else_condition, "commands": [{"goto": {"target": self.target(scene_id, fallback, path)}}]}})
            return commands
        if action.kind == "random":
            self.needs_state = True
            branches = normalize_random(value, path)
            self.random_index += 1
            state_key = f"__random_{self.random_index}"
            total = sum(weight for _, weight in branches)
            commands: list[dict[str, Any]] = [{"eval": {"script": f"__milo_state[{json.dumps(state_key)}] = Math.random() * {json.dumps(total)};"}}]
            lower = 0.0
            for index, (target, weight) in enumerate(branches):
                upper = lower + weight
                condition = (
                    f"__milo_state[{json.dumps(state_key)}] >= {json.dumps(lower)} && "
                    f"__milo_state[{json.dumps(state_key)}] < {json.dumps(upper)}"
                )
                if index == len(branches) - 1:
                    condition = f"__milo_state[{json.dumps(state_key)}] >= {json.dumps(lower)}"
                commands.append({"if": {"condition": condition, "commands": [{"goto": {"target": self.target(scene_id, target, path)}}]}})
                lower = upper
            return commands
        if action.kind == "set":
            self.needs_state = True
            expression = parse_set(value, set(self.bundle.runtime.state), path)
            return [{"eval": {"script": set_to_js(expression)}}]
        if action.kind == "prompt":
            self.needs_state = True
            data = value if isinstance(value, dict) else {"variable": value}
            variable = data["variable"]
            prompt_name = f"__milo_prompt_{variable}"
            commands: list[dict[str, Any]] = []
            if data.get("label"):
                commands.append({"say": {"label": data["label"]}})
            payload = copy.deepcopy(data)
            payload.pop("label", None)
            payload["variable"] = prompt_name
            commands.append({"prompt": payload})
            commands.append({"eval": {"script": f"__milo_state[{json.dumps(variable, ensure_ascii=False)}] = {prompt_name};"}})
            return commands
        if action.kind == "notification":
            self.needs_notification = True
            if isinstance(value, str):
                notification_id = "milo-" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]
                return [{"notification.create": {"id": notification_id, "title": value}}]
            if value.get("remove"):
                payload = copy.deepcopy(value)
                for field in ("remove", "button", "button_label", "to"):
                    payload.pop(field, None)
                payload["id"] = value["remove"]
                return [{"notification.remove": payload}]
            notification_id = value.get("id") or "milo-" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]
            payload = copy.deepcopy(value)
            for field in ("button", "button_label", "to", "remove"):
                payload.pop(field, None)
            payload["id"] = notification_id
            payload.setdefault("title", "")
            if value.get("button") or value.get("button_label"):
                payload["buttonLabel"] = value.get("button") or value.get("button_label")
            if value.get("to"):
                payload["buttonCommands"] = [{"goto": {"target": self.target(scene_id, value["to"], path)}}]
            return [{"notification.create": payload}]
        if action.kind == "preload":
            data = copy.deepcopy(value)
            target = self.target(scene_id, data.get("to"), path)
            media_commands, stats = self.preload_catalog()
            if not media_commands:
                return [{"goto": {"target": target}}]
            self.needs_preload = True
            self.needs_notification = True
            if stats["audio"]:
                self.needs_audio = True
            button = data.get("button", "Start preload")
            message_template = data.get("message", "Click to start preloading. Estimated load: {size}.")
            notification_template = data.get("notification", "Loading {percent}%  {bar}")
            notification_id = data.get("id") or "milo-preload"
            bar_width = data.get("bar_width", 10)
            message = self.render_preload_text(message_template, stats, 0, bar_width)
            initial_title = self.render_preload_text(notification_template, stats, 0, bar_width)
            start_script = (
                "__miloPreloadStart("
                + json.dumps(notification_id, ensure_ascii=False)
                + ","
                + json.dumps(target, ensure_ascii=False)
                + ","
                + str(stats["total"])
                + ","
                + str(stats["bytes"])
                + ","
                + json.dumps(notification_template, ensure_ascii=False)
                + ","
                + str(bar_width)
                + '); pages.goto("'
                + PRELOAD_PAGE_ID
                + '");'
            )
            return [
                {"say": {"label": message, "mode": "instant"}},
                {"choice": {"options": [{
                    "label": button,
                    "commands": [
                        {"notification.create": {"id": notification_id, "title": initial_title}},
                        {"eval": {"script": start_script}},
                    ],
                }]}},
            ]
        if action.kind == "end":
            return [{"end": {}}]
        raise _problem("ACTION_UNKNOWN", f"Unknown action: {action.kind}", path)

    def compile_pages(self) -> dict[str, list[dict[str, Any]]]:
        outline_entry = self.bundle.outline.entry
        entry_scene = self.bundle.scenes[outline_entry]
        pages: dict[str, list[dict[str, Any]]] = {}
        for scene_id in self.bundle.outline.nodes:
            scene = self.bundle.scenes[scene_id]
            for page_id, page in scene.pages.items():
                compiled: list[dict[str, Any]] = []
                for action in page.actions:
                    compiled.extend(self.compile_action(scene_id, action))
                pages[self.page_id(scene_id, page_id)] = compiled
        if self.needs_preload:
            _, stats = self.preload_catalog()
            batches = self.preload_batches()
            loaded_count = 0
            loaded_bytes = 0
            for index, (batch_commands, batch_sizes) in enumerate(batches):
                page_id = PRELOAD_PAGE_ID if index == 0 else f"{PRELOAD_PAGE_ID}-{index + 1:03d}"
                if page_id in pages:
                    raise _problem("PRELOAD_PAGE_COLLISION", f"Reserved Page ID is already in use: {page_id}", "pages")
                loaded_count += len(batch_commands)
                loaded_bytes += sum(batch_sizes)
                is_last = index == len(batches) - 1
                if is_last:
                    percent = 100
                    script = f"__miloPreloadAdvance({loaded_count},100); __miloPreloadComplete();"
                else:
                    if stats["bytes"] > 0:
                        percent = min(99, int((loaded_bytes * 100) / stats["bytes"]))
                    else:
                        percent = min(99, int((loaded_count * 100) / stats["total"]))
                    next_page = f"{PRELOAD_PAGE_ID}-{index + 2:03d}"
                    script = f"__miloPreloadAdvance({loaded_count},{percent}); pages.goto({json.dumps(next_page)});"
                pages[page_id] = [
                    {"eval": {"script": script}},
                    *copy.deepcopy(batch_commands),
                ]
        if "start" not in pages:
            pages = {"start": [{"goto": {"target": entry_scene.entry}}], **pages}
        return pages


def _walk_commands(commands: Any, path: str, visit: Any) -> None:
    if not isinstance(commands, list):
        raise _problem("EOS_COMMANDS", "EOS commands must be a list.", path)
    for index, command in enumerate(commands):
        command_path = f"{path}[{index}]"
        if not isinstance(command, dict) or len(command) != 1:
            raise _problem("EOS_COMMAND", "An EOS command must be a single-key object.", command_path)
        kind, payload = next(iter(command.items()))
        if not isinstance(kind, str) or not kind:
            raise _problem("EOS_COMMAND", "An EOS command name must be a non-empty string.", command_path)
        visit(kind, payload, command_path)
        if not isinstance(payload, dict):
            continue
        options = payload.get("options")
        if options is not None:
            if not isinstance(options, list):
                raise _problem("EOS_OPTIONS", "EOS options must be a list.", f"{command_path}.options")
            for option_index, option in enumerate(options):
                if isinstance(option, dict) and "commands" in option:
                    _walk_commands(option["commands"], f"{command_path}.options[{option_index}].commands", visit)
        for key, nested in payload.items():
            if key in {"commands", "elseCommands", "buttonCommands", "timerCommands"}:
                _walk_commands(nested, f"{command_path}.{key}", visit)
            elif key.endswith("Commands") and isinstance(nested, list):
                # Future command arrays are traversed when their shape is
                # recognizable. Opaque future payload fields stay untouched.
                _walk_commands(nested, f"{command_path}.{key}", visit)


def validate_eos(script: dict[str, Any]) -> tuple[SourceIssue, ...]:
    pages = script.get("pages")
    files = script.get("files")
    galleries = script.get("galleries")
    modules = script.get("modules")
    if not isinstance(pages, dict) or not pages or "start" not in pages:
        raise _problem("EOS_PAGES", "EOS must contain non-empty pages and start fields.", "eosscript.json.pages")
    if files is not None and not isinstance(files, dict):
        raise _problem("EOS_CATALOG", "EOS files must be an object.", "eosscript.json.files")
    if galleries is not None and not isinstance(galleries, dict):
        raise _problem("EOS_CATALOG", "EOS galleries must be an object.", "eosscript.json.galleries")
    if modules is not None and not isinstance(modules, dict):
        raise _problem("EOS_CATALOG", "EOS modules must be an object.", "eosscript.json.modules")
    files = files or {}
    galleries = galleries or {}
    modules = modules or {}
    page_ids = set(pages)
    goto_edges: dict[str, set[str]] = defaultdict(set)
    warnings: list[SourceIssue] = []
    required_modules: set[str] = set()

    for page_id, commands in pages.items():
        current_page = page_id

        def record_target(target: Any, path: str) -> None:
            if target not in page_ids:
                matches = sorted(
                    page for page in page_ids
                    if isinstance(target, str) and "*" in target and fnmatch.fnmatch(page, target)
                )
                if matches:
                    goto_edges[current_page].update(matches)
                else:
                    warnings.append(SourceIssue("warning", "EOS_DYNAMIC_TARGET", f"goto target cannot be resolved statically: {target}", path))
            else:
                goto_edges[current_page].add(target)

        def visit(kind: str, payload: Any, path: str) -> None:
            if kind == "audio.stop":
                raise _problem("EOS_COMMAND_UNSUPPORTED", "The current EOS Runtime does not support audio.stop; use eval to call Sound.get(id).stop().", path)
            if kind not in KNOWN_EOS_COMMANDS:
                warnings.append(SourceIssue("warning", "EOS_COMMAND_UNKNOWN", f"Unrecognized EOS command was preserved unchanged: {kind}", path))
            if kind == "goto":
                target = payload.get("target") if isinstance(payload, dict) else None
                record_target(target, path)
            if kind == "choice" and isinstance(payload, dict) and isinstance(payload.get("options"), list):
                for option_index, option in enumerate(payload["options"]):
                    if isinstance(option, dict) and "target" in option:
                        record_target(option.get("target"), f"{path}.options[{option_index}].target")
            if kind in {"enable", "disable"}:
                target = payload.get("target") if isinstance(payload, dict) else None
                if not isinstance(target, str) or not target.strip():
                    raise _problem("EOS_PAGE_PATTERN", f"{kind} command is missing a page target.", path)
                matches = target in page_ids or any(fnmatch.fnmatch(page, target) for page in page_ids)
                if not matches:
                    warnings.append(SourceIssue(
                        "warning",
                        "EOS_PAGE_PATTERN",
                        f"{kind} page target matched no Page and was preserved unchanged: {target}",
                        path,
                    ))
            if kind in {"image", "audio.play"}:
                locator = payload.get("locator") if isinstance(payload, dict) else None
                if not isinstance(locator, str):
                    raise _problem("EOS_LOCATOR", "Media command is missing a locator.", path)
                if locator == "":
                    pass
                elif locator.startswith("file:"):
                    name = locator[5:]
                    if "*" not in name and name not in files:
                        warnings.append(SourceIssue("warning", "EOS_FILE_REFERENCE", f"file locator is not declared in the catalog: {name}", path))
                elif locator.startswith("gallery:"):
                    gallery_id, _, image_id = locator[8:].partition("/")
                    if gallery_id not in galleries:
                        warnings.append(SourceIssue("warning", "EOS_GALLERY_REFERENCE", f"gallery locator is not declared in the catalog: {gallery_id}", path))
                        return
                    if image_id and image_id != "*":
                        known = {str(image.get("id")) for image in galleries[gallery_id].get("images", []) if isinstance(image, dict)}
                        if image_id not in known:
                            warnings.append(SourceIssue("warning", "EOS_IMAGE_REFERENCE", f"gallery image is not declared in the catalog: {image_id}", path))
                else:
                    warnings.append(SourceIssue("warning", "EOS_LOCATOR_UNKNOWN", f"Unrecognized media locator was preserved unchanged: {locator}", path))
            if kind.startswith("audio."):
                required_modules.add("audio")
            if kind.startswith("notification."):
                required_modules.add("notification")
            if kind == "storage" or kind.startswith("storage."):
                required_modules.add("storage")

        _walk_commands(commands, f"eosscript.json.pages.{page_id}", visit)

    missing_modules = required_modules - set(modules)
    if missing_modules:
        raise _problem("EOS_MODULE", f"Missing EOS module: {', '.join(sorted(missing_modules))}", "eosscript.json.modules")
    reached: set[str] = set()
    queue = ["start"]
    while queue:
        page_id = queue.pop(0)
        if page_id in reached:
            continue
        reached.add(page_id)
        queue.extend(sorted(goto_edges.get(page_id, set())))
    for page_id in sorted(page_ids - reached):
        if page_id.startswith("--milo-preload-"):
            continue
        warnings.append(SourceIssue("warning", "EOS_UNREACHABLE", "Compiled Page is unreachable.", f"eosscript.json.pages.{page_id}"))
    return tuple(warnings)


def compile_sources(bundle: SourceBundle, project_dir: Path) -> BuildProduct:
    bundle, inline_references = _prepare_inline_assets(bundle, project_dir.resolve())
    source_warnings = validate_bundle(bundle)
    assets, generated_files, generated_galleries, materialized_paths = materialize_assets(project_dir, bundle)
    raw_script = copy.deepcopy(bundle.runtime.eos)
    raw_files = raw_script.get("files") if isinstance(raw_script.get("files"), dict) else {}
    raw_galleries = raw_script.get("galleries") if isinstance(raw_script.get("galleries"), dict) else {}
    files = _merge_catalog(raw_files, generated_files, "files")
    galleries = _merge_catalog(raw_galleries, generated_galleries, "galleries")
    compiler = _Compiler(bundle, assets, files, galleries, inline_references)
    pages = compiler.compile_pages()
    modules = copy.deepcopy(raw_script.get("modules")) if isinstance(raw_script.get("modules"), dict) else {}
    if compiler.needs_audio:
        modules.setdefault("audio", {})
    if compiler.needs_notification:
        modules.setdefault("notification", {})
    script = raw_script
    script["pages"] = pages
    if files or "files" in raw_script or generated_files:
        script["files"] = files
    if galleries or "galleries" in raw_script or generated_galleries:
        script["galleries"] = galleries
    if modules or "modules" in raw_script:
        script["modules"] = modules
    if compiler.needs_preload:
        raw_init = script.get("init", "")
        script["init"] = PRELOAD_HELPER_JS + (f"\n{raw_init}" if raw_init else "")
    if bundle.runtime.state or compiler.needs_state:
        init_state = json.dumps(bundle.runtime.state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        prefix = f"var __milo_state={init_state};"
        raw_init = script.get("init", "")
        script["init"] = prefix + (f"\n{raw_init}" if raw_init else "")
    script = _normalize_all_eos_durations(script)
    eos_warnings = validate_eos(script)
    return BuildProduct(script=script, warnings=tuple((*source_warnings, *eos_warnings)), materialized_files=materialized_paths)


def compile_project(project_dir: Path) -> BuildProduct:
    resolved = project_dir.resolve()
    return compile_sources(load_project_sources(resolved), resolved)
