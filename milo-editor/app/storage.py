from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import os
import re
import shutil
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from PIL import Image

from .config import PROJECTS_ROOT
from .milo_ir import MiloSourceError, compile_project, parse_outline
from .milo_ir.migration import migrate_project_dir


PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
WINDOWS_INVALID_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
MEDIA_FOLDER_TYPES = {"image", "audio"}


class StoreError(RuntimeError):
    pass


class NotFoundError(StoreError):
    pass


class ValidationError(StoreError):
    pass


class GeneratedArtifactReadOnlyError(ValidationError):
    code = "GENERATED_ARTIFACT_READ_ONLY"

    def __init__(self) -> None:
        super().__init__("GENERATED_ARTIFACT_READ_ONLY\nEdit Milo IR and rebuild this project.")


SOURCE_MODES = {"legacy-eos", "milo-ir"}
DEFAULT_OUTLINE = """format: milo-outline
title: {title}
brief: Describe the overall direction, experience, and structure of the work here
entry: opening
nodes:
  opening:
    name: Opening
    content: Describe the opening story, media, interactions, and design intent here
    next: []
"""
DEFAULT_MILO = """format: milo-runtime
state: {}
assets: {}
files: {}
galleries: {}
modules: {}
init: ''
info: {}
"""
DEFAULT_SCENE = """format: milo-ir
scene: opening
entry: start
pages:
  start:
    - say: New Milo IR project
    - end: true
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_project_id(value: str) -> str:
    if not PROJECT_ID_RE.fullmatch(value or ""):
        raise ValidationError("Invalid project id")
    return value


def safe_filename(value: str) -> str:
    name = Path(value or "upload").name.strip()
    name = SAFE_NAME_RE.sub("_", name).strip(" .")
    return (name or "upload")[:160]


def safe_media_name(value: str, *, label: str = "name", max_length: int = 240) -> str:
    """Validate one Windows-compatible path component without destroying Unicode."""
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} cannot be empty")
    if value in {".", ".."} or WINDOWS_INVALID_NAME_RE.search(value):
        raise ValidationError(f"{label} contains characters not allowed by Windows")
    if value[-1] in {" ", "."}:
        raise ValidationError(f"{label} cannot end with a space or period")
    if len(value) > max_length:
        raise ValidationError(f"{label} is too long")
    stem = value.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise ValidationError(f"{label} is a reserved Windows name")
    return value


class ProjectStore:
    def __init__(self, root: Path = PROJECTS_ROOT):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def project_dir(self, project_id: str) -> Path:
        return self.root / safe_project_id(project_id)

    def _metadata_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"

    def _script_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "eosscript.json"

    def _outline_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "outline.yaml"

    def _milo_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "milo.yaml"

    def _source_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "src"

    def _tease_graph_layout_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "tease-graph-layout.json"

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise NotFoundError(path.name) from exc
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON in {path.name}: {exc}") from exc

    @staticmethod
    def _atomic_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            # Keep failed temporary files for diagnosis; this project never deletes files.
            raise

    @staticmethod
    def _atomic_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text.rstrip() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            raise

    @staticmethod
    def _atomic_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            raise

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for child in sorted(self.root.iterdir(), key=lambda path: path.name.lower()):
            if not child.is_dir() or not (child / "project.json").is_file():
                continue
            metadata = self._read_json(child / "project.json")
            metadata["id"] = child.name
            projects.append(metadata)
        return projects

    def get_project(self, project_id: str) -> dict[str, Any]:
        metadata = self._read_json(self._metadata_path(project_id))
        metadata["id"] = safe_project_id(project_id)
        return metadata

    def create_project(
        self,
        project_id: str,
        title: str,
        author: str = "Local Author",
        script: dict[str, Any] | None = None,
        source_mode: str = "legacy-eos",
    ) -> dict[str, Any]:
        project_id = safe_project_id(project_id)
        if source_mode not in SOURCE_MODES:
            raise ValidationError("sourceMode must be legacy-eos or milo-ir")
        if source_mode == "milo-ir" and script is not None:
            raise ValidationError("Milo IR projects do not accept an EOS script at creation")
        project_dir = self.project_dir(project_id)
        with self._lock:
            if self._metadata_path(project_id).exists():
                raise ValidationError("Project already exists")
            project_dir.mkdir(parents=True, exist_ok=True)
            for name in ("history", "media/timg/tb_xl", "media/archive", "storage"):
                (project_dir / name).mkdir(parents=True, exist_ok=True)
            now = utc_now()
            metadata = {
                "id": project_id,
                "title": title.strip() or project_id,
                "author": author.strip() or "Local Author",
                "createdAt": now,
                "updatedAt": now,
                "status": "draft",
                "sourceMode": source_mode,
            }
            self._atomic_json(self._metadata_path(project_id), metadata)
            if source_mode == "milo-ir":
                title_yaml = json.dumps(metadata["title"], ensure_ascii=False)
                self._atomic_text(self._outline_path(project_id), DEFAULT_OUTLINE.format(title=title_yaml))
                self._atomic_text(self._milo_path(project_id), DEFAULT_MILO)
                self._atomic_text(self._source_dir(project_id) / "opening.milo.yaml", DEFAULT_SCENE)
                product = compile_project(project_dir)
                self._atomic_json(self._script_path(project_id), product.script)
            else:
                base_script = script if script is not None else {
                    "pages": {"start": [{"say": {"label": "New local EOS project"}}]},
                    "files": {},
                    "modules": {},
                    "galleries": {},
                    "init": "",
                }
                self._validate_script(base_script)
                self._atomic_json(self._script_path(project_id), base_script)
        return self.get_project(project_id)

    def source_mode(self, project_id: str) -> str:
        mode = self.get_project(project_id).get("sourceMode", "legacy-eos")
        return mode if mode in SOURCE_MODES else "legacy-eos"

    def _assert_script_writable(self, project_id: str) -> None:
        if self.source_mode(project_id) == "milo-ir":
            raise GeneratedArtifactReadOnlyError()

    def next_numeric_project_id(self) -> str:
        numeric_ids = [int(item["id"]) for item in self.list_projects() if str(item["id"]).isdigit()]
        return str(max(numeric_ids, default=100000) + 1)

    @staticmethod
    def _validate_script(script: Any) -> None:
        if not isinstance(script, dict):
            raise ValidationError("EOS script must be a JSON object")
        if "pages" not in script or not isinstance(script["pages"], dict):
            raise ValidationError("EOS script must contain a pages object")
        for optional in ("files", "galleries", "modules"):
            if optional in script and not isinstance(script[optional], dict):
                raise ValidationError(f"EOS script field {optional} must be an object")

    def load_script(self, project_id: str) -> dict[str, Any]:
        script = self._read_json(self._script_path(project_id))
        self._validate_script(script)
        return script

    def list_galleries(self, project_id: str) -> list[dict[str, Any]]:
        """Return the current EOS galleries and the local files they reference."""
        script = self.load_script(project_id)
        project_dir = self.project_dir(project_id)
        galleries = script.get("galleries") or {}
        if not isinstance(galleries, dict):
            raise ValidationError("EOS script galleries must be an object")

        # Build the hash index once so gallery metadata can resolve any local
        # image extension (PNG, JPEG, WebP, ...), not only the JPEG thumbnail
        # layout used by newly uploaded files.
        media_by_hash = {
            str(record.get("hash", "")).casefold(): record
            for record in self._media_records(project_id)
            if record.get("hash")
        }
        result: list[dict[str, Any]] = []
        for gallery_id, raw_gallery in galleries.items():
            if not isinstance(raw_gallery, dict):
                continue
            gallery_name = str(raw_gallery.get("name") or gallery_id)
            images = raw_gallery.get("images") or []
            if not isinstance(images, list):
                raise ValidationError(f"Gallery {gallery_id} images must be a list")
            scanned_images: list[dict[str, Any]] = []
            safe_gallery_name = safe_filename(gallery_name)
            for raw_image in images:
                if not isinstance(raw_image, dict) or raw_image.get("id") is None:
                    continue
                image_id = str(raw_image["id"])
                locator = f"gallery:{gallery_id}/{image_id}"
                candidates = [
                    project_dir / "media" / "timg" / "tb_xl" / f"{raw_image.get('hash', '')}.jpg",
                    project_dir / "media" / "galleries" / safe_gallery_name / f"{raw_image.get('hash', '')}.jpg",
                    project_dir / "media" / "galleries" / safe_gallery_name / f"{image_id}.jpg",
                ]
                local_path = next((candidate for candidate in candidates if candidate.is_file()), None)
                indexed_record = media_by_hash.get(str(raw_image.get("hash", "")).casefold())
                if local_path is None and indexed_record:
                    local_path = project_dir / indexed_record["path"]
                item = {
                    "id": image_id,
                    "hash": raw_image.get("hash"),
                    "size": raw_image.get("size"),
                    "width": raw_image.get("width"),
                    "height": raw_image.get("height"),
                    "locator": locator,
                    "available": local_path is not None,
                }
                if local_path is not None:
                    item["path"] = str(local_path.relative_to(project_dir)).replace("\\", "/")
                scanned_images.append(item)
            result.append({
                "id": str(gallery_id),
                "name": gallery_name,
                "imageCount": len(scanned_images),
                "availableCount": sum(1 for image in scanned_images if image["available"]),
                "images": scanned_images,
            })
        return result

    def _write_script_version(self, project_id: str, script: dict[str, Any]) -> dict[str, Any]:
        self._validate_script(script)
        script_path = self._script_path(project_id)
        metadata_path = self._metadata_path(project_id)
        with self._lock:
            if not metadata_path.exists():
                raise NotFoundError(project_id)
            history_path: Path | None = None
            if script_path.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
                history_path = self.project_dir(project_id) / "history" / f"eosscript-{stamp}.json"
                history_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(script_path, history_path)
            self._atomic_json(script_path, script)
            metadata = self._read_json(metadata_path)
            metadata["updatedAt"] = utc_now()
            if history_path is not None:
                metadata["lastHistoryFile"] = history_path.name
            self._atomic_json(metadata_path, metadata)
        result = {"saved": True, "updatedAt": metadata["updatedAt"]}
        if history_path is not None:
            result["history"] = history_path.name
        return result

    def save_script(self, project_id: str, script: dict[str, Any]) -> dict[str, Any]:
        self._assert_script_writable(project_id)
        return self._write_script_version(project_id, script)

    def write_generated_script(self, project_id: str, script: dict[str, Any]) -> dict[str, Any]:
        if self.source_mode(project_id) != "milo-ir":
            raise ValidationError("Generated script writer is only available for milo-ir projects")
        return self._write_script_version(project_id, script)

    def load_outline(self, project_id: str) -> str:
        self.get_project(project_id)
        try:
            return self._outline_path(project_id).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise NotFoundError("outline.yaml") from exc

    def save_outline(self, project_id: str, text: str) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValidationError("Outline YAML must not be empty")
        if len(text.encode("utf-8")) > 2_000_000:
            raise ValidationError("Outline YAML exceeds the 2 MB limit")
        self.get_project(project_id)
        if self.source_mode(project_id) == "milo-ir":
            try:
                parse_outline(text)
            except MiloSourceError as exc:
                raise ValidationError(str(exc)) from exc
        path = self._outline_path(project_id)
        metadata_path = self._metadata_path(project_id)
        with self._lock:
            if path.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
                history_path = self.project_dir(project_id) / "history" / f"outline-{stamp}.yaml"
                history_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, history_path)
            self._atomic_text(path, text)
            metadata = self._read_json(metadata_path)
            metadata["updatedAt"] = utc_now()
            self._atomic_json(metadata_path, metadata)
        return {"saved": True, "updatedAt": metadata["updatedAt"]}

    @staticmethod
    def _validate_tease_graph_layout(layout: Any) -> dict[str, Any]:
        if not isinstance(layout, dict):
            raise ValidationError("Tease Graph layout must be a JSON object")
        if layout.get("version") != 1:
            raise ValidationError("Tease Graph layout version must be 1")
        nodes = layout.get("nodes")
        if not isinstance(nodes, dict):
            raise ValidationError("Tease Graph layout nodes must be an object")
        if len(nodes) > 10_000:
            raise ValidationError("Tease Graph layout exceeds the 10,000 node limit")

        normalized_nodes: dict[str, dict[str, float]] = {}
        for node_id, position in nodes.items():
            if not isinstance(node_id, str) or not node_id or len(node_id) > 240:
                raise ValidationError("Tease Graph layout contains an invalid node id")
            if not isinstance(position, dict):
                raise ValidationError(f"Tease Graph layout position for {node_id} must be an object")
            x = position.get("x")
            y = position.get("y")
            for axis, value in (("x", x), ("y", y)):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValidationError(f"Tease Graph layout {node_id}.{axis} must be a finite number")
                if abs(value) > 10_000_000:
                    raise ValidationError(f"Tease Graph layout {node_id}.{axis} is out of range")
            normalized_nodes[node_id] = {"x": float(x), "y": float(y)}

        normalized = {"version": 1, "nodes": normalized_nodes}
        edges = layout.get("edges")
        if edges is not None:
            if not isinstance(edges, dict):
                raise ValidationError("Tease Graph layout edges must be an object")
            if len(edges) > 20_000:
                raise ValidationError("Tease Graph layout exceeds the 20,000 edge limit")
            normalized_edges: dict[str, list[dict[str, float]]] = {}
            for edge_id, points in edges.items():
                if not isinstance(edge_id, str) or not edge_id or len(edge_id) > 500:
                    raise ValidationError("Tease Graph layout contains an invalid edge id")
                if not isinstance(points, list) or not 2 <= len(points) <= 512:
                    raise ValidationError(f"Tease Graph layout route for {edge_id} must contain 2 to 512 points")
                normalized_points: list[dict[str, float]] = []
                for index, point in enumerate(points):
                    if not isinstance(point, dict):
                        raise ValidationError(f"Tease Graph layout route point {edge_id}[{index}] must be an object")
                    x = point.get("x")
                    y = point.get("y")
                    for axis, value in (("x", x), ("y", y)):
                        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                            raise ValidationError(f"Tease Graph layout {edge_id}[{index}].{axis} must be a finite number")
                        if abs(value) > 10_000_000:
                            raise ValidationError(f"Tease Graph layout {edge_id}[{index}].{axis} is out of range")
                    normalized_points.append({"x": float(x), "y": float(y)})
                normalized_edges[edge_id] = normalized_points
            normalized["edges"] = normalized_edges

        return normalized

    def load_tease_graph_layout(self, project_id: str) -> dict[str, Any]:
        self.get_project(project_id)
        return self._validate_tease_graph_layout(self._read_json(self._tease_graph_layout_path(project_id)))

    def save_tease_graph_layout(self, project_id: str, layout: Any) -> dict[str, Any]:
        self.get_project(project_id)
        normalized = self._validate_tease_graph_layout(layout)
        with self._lock:
            self._atomic_json(self._tease_graph_layout_path(project_id), normalized)
        return {"saved": True, "nodeCount": len(normalized["nodes"])}

    @staticmethod
    def _merge_patch(target: Any, patch: Any) -> Any:
        """Apply JSON Merge Patch (RFC 7396) without dropping unknown EOS fields."""
        if not isinstance(patch, dict):
            return deepcopy(patch)
        result = deepcopy(target) if isinstance(target, dict) else {}
        for key, value in patch.items():
            if value is None:
                result.pop(key, None)
            else:
                result[key] = ProjectStore._merge_patch(result.get(key), value)
        return result

    def apply_script_patches(self, project_id: str, patches: list[str | dict[str, Any]]) -> dict[str, Any]:
        self._assert_script_writable(project_id)
        script: Any = self.load_script(project_id)
        for raw_patch in patches:
            patch = json.loads(raw_patch) if isinstance(raw_patch, str) else raw_patch
            script = self._merge_patch(script, patch)
        return self.save_script(project_id, script)

    def update_project(self, project_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {"title", "author", "status"}
        with self._lock:
            metadata = self.get_project(project_id)
            metadata.update({key: value for key, value in updates.items() if key in allowed})
            metadata["updatedAt"] = utc_now()
            metadata.pop("id", None)
            self._atomic_json(self._metadata_path(project_id), metadata)
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        """Remove a project from the active list by moving it to a recoverable archive."""
        project_id = safe_project_id(project_id)
        project_dir = self.project_dir(project_id)
        root = self.root.resolve()
        target = project_dir.resolve(strict=False)
        if target == root or root not in target.parents:
            raise ValidationError("Project path is outside the local projects root")

        with self._lock:
            if not self._metadata_path(project_id).is_file() or not project_dir.is_dir():
                raise NotFoundError(project_id)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            archive_root = root / "_archived_projects"
            destination = archive_root / f"{project_id}-{stamp}"
            if archive_root.resolve(strict=False) != root and root not in archive_root.resolve(strict=False).parents:
                raise ValidationError("Project archive path is outside the local projects root")
            archive_root.mkdir(parents=True, exist_ok=True)
            shutil.move(str(project_dir), str(destination))
        return True

    def load_storage(self, project_id: str) -> str:
        path = self.project_dir(project_id) / "storage" / "state.json"
        return path.read_text(encoding="utf-8") if path.exists() else "{}"

    def save_storage(self, project_id: str, state: str) -> bool:
        self.get_project(project_id)
        try:
            json.loads(state)
        except json.JSONDecodeError as exc:
            raise ValidationError("Storage state must be valid JSON text") from exc
        path = self.project_dir(project_id) / "storage" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(state)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        return True

    def _media_records(self, project_id: str) -> list[dict[str, Any]]:
        project_dir = self.project_dir(project_id)
        indexed: dict[str, dict[str, Any]] = {}
        media_root = project_dir / "media"
        if media_root.exists():
            for index_path in media_root.rglob("index.json"):
                entries = self._read_json(index_path)
                if isinstance(entries, list):
                    indexed.update({str(item.get("path")): item for item in entries if isinstance(item, dict) and item.get("path")})
        records: list[dict[str, Any]] = []
        for kind in ("timg", "files", "galleries", "sources"):
            base = project_dir / "media" / kind
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file() and path.name != "index.json":
                    stat = path.stat()
                    relative = str(path.relative_to(project_dir)).replace("\\", "/")
                    metadata = indexed.get(relative, {})
                    digest = metadata.get("hash") or path.stem.split(".duplicate-", 1)[0]
                    records.append({
                        "id": metadata.get("id", self._numeric_id(digest)),
                        "name": metadata.get("name", path.name),
                        "hash": digest,
                        "path": relative,
                        "kind": metadata.get("kind", "file"),
                        "size": stat.st_size,
                        "mimeType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                        "updatedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    })
        return records

    @staticmethod
    def _numeric_id(value: str) -> int:
        return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF

    def find_media_by_hash(self, project_id: str, digest: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"[A-Fa-f0-9]{40}", digest or ""):
            return None
        for record in self._media_records(project_id):
            if record["hash"].casefold() == digest.casefold():
                width = height = None
                path = self.project_dir(project_id) / record["path"]
                if record["mimeType"].startswith("image/"):
                    with Image.open(path) as image:
                        width, height = image.size
                return {
                    "id": record["id"],
                    "hash": digest.lower(),
                    "size": record["size"],
                    "mimeType": record["mimeType"],
                    "dimensions": {"width": width, "height": height},
                    "path": record["path"],
                }
        return None

    def list_media(self, project_id: str, query: str = "") -> list[dict[str, Any]]:
        records = self._media_records(project_id)
        if query:
            needle = query.casefold()
            records = [item for item in records if needle in item["name"].casefold()]
        return sorted(records, key=lambda item: item["name"].casefold())

    def list_source_media(self, project_id: str, query: str = "") -> list[dict[str, Any]]:
        """List editable author media without exposing generated EOS catalogs."""
        self.get_project(project_id)
        records = [
            item for item in self._media_records(project_id)
            if item["path"].startswith("media/sources/")
            and (item["mimeType"].startswith("image/") or item["mimeType"].startswith("audio/"))
        ]
        if query:
            needle = query.casefold()
            records = [item for item in records if needle in f"{item['name']} {item['path']}".casefold()]
        return sorted(records, key=lambda item: (item["path"].casefold(), item["name"].casefold()))

    def _source_folder_types_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "media-folder-types.json"

    def _read_source_folder_types(self, project_id: str) -> dict[str, list[str]]:
        path = self._source_folder_types_path(project_id)
        if not path.exists():
            return {}
        raw = self._read_json(path)
        folders = raw.get("folders") if isinstance(raw, dict) else None
        if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(folders, dict):
            raise ValidationError("media-folder-types.json has an invalid format")
        normalized: dict[str, list[str]] = {}
        for folder, raw_types in folders.items():
            if not isinstance(folder, str) or not isinstance(raw_types, list):
                raise ValidationError("media-folder-types.json contains an invalid folder record")
            types = sorted({value for value in raw_types if value in MEDIA_FOLDER_TYPES})
            if types:
                normalized[folder.replace("\\", "/").rstrip("/")] = types
        return normalized

    def _write_source_folder_types(self, project_id: str, folders: dict[str, list[str]]) -> None:
        normalized = {
            folder.replace("\\", "/").rstrip("/"): sorted(set(types))
            for folder, types in folders.items() if types
        }
        self._atomic_json(self._source_folder_types_path(project_id), {"version": 1, "folders": normalized})

    def _resolve_source_folder(self, project_id: str, relative_folder: str, *, must_exist: bool = False) -> tuple[Path, Path, Path]:
        self.get_project(project_id)
        normalized = str(relative_folder or "").replace("\\", "/").strip("/")
        parts = normalized.split("/") if normalized else []
        if len(parts) < 2 or parts[:2] != ["media", "sources"] or any(part in {"", ".", ".."} for part in parts):
            raise ValidationError("The folder must be media/sources or one of its subdirectories")
        for part in parts[2:]:
            safe_media_name(part, label="folder name")
        project_dir = self.project_dir(project_id).resolve()
        source_root = (project_dir / "media" / "sources").resolve()
        folder = project_dir.joinpath(*parts).resolve()
        if folder != source_root and source_root not in folder.parents:
            raise ValidationError("The folder escapes media/sources")
        if must_exist and not folder.is_dir():
            raise NotFoundError(normalized)
        return project_dir, source_root, folder

    @staticmethod
    def _natural_name_key(value: str) -> tuple[tuple[int, Any], ...]:
        return tuple(
            (1, int(part)) if part.isdigit() else (0, part.casefold(), part)
            for part in re.split(r"(\d+)", value)
        )

    def list_source_folders(self, project_id: str) -> list[dict[str, Any]]:
        project_dir, source_root, _ = self._resolve_source_folder(project_id, "media/sources")
        if not source_root.is_dir():
            return []
        folders = [
            path for path in source_root.rglob("*")
            if path.is_dir() and source_root in path.resolve().parents
        ]
        folder_types: dict[str, set[str]] = {
            folder.relative_to(project_dir).as_posix(): set() for folder in folders
        }

        for path in source_root.rglob("*"):
            if not path.is_file():
                continue
            mime_type = mimetypes.guess_type(path.name)[0] or ""
            media_type = "image" if mime_type.startswith("image/") else "audio" if mime_type.startswith("audio/") else None
            if media_type is None:
                continue
            parent = path.parent
            while parent != source_root:
                relative = parent.relative_to(project_dir).as_posix()
                if relative in folder_types:
                    folder_types[relative].add(media_type)
                parent = parent.parent

        metadata = self._read_source_folder_types(project_id)
        for metadata_path, types in metadata.items():
            for folder_path, inferred in folder_types.items():
                if metadata_path == folder_path or metadata_path.startswith(f"{folder_path}/"):
                    inferred.update(types)

        result = []
        for folder in folders:
            path = folder.relative_to(project_dir).as_posix()
            result.append({
                "path": path,
                "name": folder.name,
                "parent": folder.parent.relative_to(project_dir).as_posix(),
                "types": sorted(folder_types[path]),
            })
        return sorted(result, key=lambda item: self._natural_name_key(item["path"]))

    def create_source_folder(self, project_id: str, parent: str, name: str, media_type: str) -> dict[str, Any]:
        if media_type not in MEDIA_FOLDER_TYPES:
            raise ValidationError("mediaType must be image or audio")
        clean_name = safe_media_name(name, label="folder name")
        with self._lock:
            project_dir, source_root, parent_path = self._resolve_source_folder(project_id, parent)
            if parent_path == source_root:
                source_root.mkdir(parents=True, exist_ok=True)
            elif not parent_path.is_dir():
                raise NotFoundError(parent)
            destination = (parent_path / clean_name).resolve()
            if source_root not in destination.parents:
                raise ValidationError("The new folder escapes media/sources")
            if destination.exists():
                raise ValidationError("A folder with the same name already exists")
            destination.mkdir()
            relative = destination.relative_to(project_dir).as_posix()
            metadata = self._read_source_folder_types(project_id)
            metadata[relative] = [media_type]
            self._write_source_folder_types(project_id, metadata)
            return {
                "path": relative,
                "name": clean_name,
                "parent": parent_path.relative_to(project_dir).as_posix(),
                "types": [media_type],
            }

    def rename_source_folder(self, project_id: str, relative_folder: str, new_name: str) -> dict[str, Any]:
        clean_name = safe_media_name(new_name, label="folder name")
        with self._lock:
            project_dir, source_root, source = self._resolve_source_folder(project_id, relative_folder, must_exist=True)
            if source == source_root:
                raise ValidationError("The media/sources root cannot be renamed")
            destination = source.with_name(clean_name)
            if destination != source and destination.exists():
                raise ValidationError("A folder with the same name already exists")
            media_root = (project_dir / "media").resolve()
            media_files = []
            for path in source.rglob("*"):
                mime_type = mimetypes.guess_type(path.name)[0] or ""
                if path.is_file() and (mime_type.startswith("image/") or mime_type.startswith("audio/")):
                    resolved_path = path.resolve()
                    if source_root not in resolved_path.parents:
                        raise ValidationError("The media file escapes media/sources")
                    media_files.append(path)
            media_files.sort(key=lambda path: self._natural_name_key(path.relative_to(source).as_posix()))
            for path in media_files:
                self._ensure_media_index_entry(project_dir, media_root, path)
            index_snapshot = self._snapshot_media_indexes(media_root)
            metadata = self._read_source_folder_types(project_id)
            metadata_snapshot = deepcopy(metadata)
            old_prefix = source.relative_to(project_dir).as_posix()
            new_prefix = destination.relative_to(project_dir).as_posix()
            changes = [
                {
                    "oldPath": path.relative_to(project_dir).as_posix(),
                    "path": f"{new_prefix}/{path.relative_to(source).as_posix()}",
                    "name": path.name,
                }
                for path in media_files
            ]
            moved = False
            metadata_written = False
            try:
                if destination != source:
                    os.replace(source, destination)
                    moved = True
                for change in changes:
                    self._rewrite_media_index_path(media_root, change["oldPath"], change["path"])
                rewritten_metadata: dict[str, list[str]] = {}
                for folder, types in metadata.items():
                    if folder == old_prefix or folder.startswith(f"{old_prefix}/"):
                        folder = new_prefix + folder[len(old_prefix):]
                    rewritten_metadata[folder] = types
                self._write_source_folder_types(project_id, rewritten_metadata)
                metadata_written = True
            except Exception:
                if moved and destination.is_dir() and not source.exists():
                    os.replace(destination, source)
                self._restore_media_indexes(index_snapshot)
                if metadata_written or self._source_folder_types_path(project_id).exists():
                    self._write_source_folder_types(project_id, metadata_snapshot)
                raise
            return {
                "folder": {"oldPath": old_prefix, "path": new_prefix, "name": clean_name},
                "changes": changes,
            }

    def auto_rename_source_media(self, project_id: str, relative_paths: list[str], prefix: str | None = None) -> dict[str, list[dict[str, str]]]:
        if not isinstance(relative_paths, list) or not relative_paths or not all(isinstance(path, str) for path in relative_paths):
            raise ValidationError("paths must be a non-empty array of strings")
        if len(set(path.replace("\\", "/").casefold() for path in relative_paths)) != len(relative_paths):
            raise ValidationError("paths cannot contain duplicate media items")
        with self._lock:
            resolved = [self._resolve_project_media_file(project_id, path, source_only=True) for path in relative_paths]
            project_dir, media_root = resolved[0][0], resolved[0][1]
            sources = [item[2] for item in resolved]
            parent = sources[0].parent
            if any(source.parent != parent for source in sources):
                raise ValidationError("Auto-rename only supports media in the same direct folder")
            clean_prefix = safe_media_name(prefix if prefix is not None else parent.name, label="filename prefix", max_length=180)
            sources.sort(key=lambda path: self._natural_name_key(path.name))
            destinations = [parent / safe_media_name(f"{clean_prefix}-{index}{source.suffix}", label="filename") for index, source in enumerate(sources, 1)]
            destination_names = [path.name.casefold() for path in destinations]
            if len(set(destination_names)) != len(destination_names):
                raise ValidationError("Auto-rename would create duplicate filenames")
            selected_names = {path.name.casefold() for path in sources}
            occupied_names = {path.name.casefold() for path in parent.iterdir() if path.is_file()}
            collisions = sorted(set(destination_names) & (occupied_names - selected_names))
            if collisions:
                raise ValidationError(f"Target filename already exists: {collisions[0]}")

            for source in sources:
                self._ensure_media_index_entry(project_dir, media_root, source)
            index_snapshot = self._snapshot_media_indexes(media_root)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            records = []
            for index, (source, destination) in enumerate(zip(sources, destinations, strict=True), 1):
                temp_path = parent / f".milo-auto-rename-{stamp}-{index}.tmp"
                while temp_path.exists():
                    index += 1
                    temp_path = parent / f".milo-auto-rename-{stamp}-{index}.tmp"
                records.append((source, temp_path, destination))
            staged: list[tuple[Path, Path, Path]] = []
            finalized: list[tuple[Path, Path, Path]] = []
            renamed: list[dict[str, str]] = []
            try:
                for record in records:
                    os.replace(record[0], record[1])
                    staged.append(record)
                for record in records:
                    os.replace(record[1], record[2])
                    finalized.append(record)
                for source, _, destination in records:
                    old_path = source.relative_to(project_dir).as_posix()
                    new_path = destination.relative_to(project_dir).as_posix()
                    self._rewrite_media_index_path(media_root, old_path, new_path, destination.name)
                    renamed.append({"oldPath": old_path, "path": new_path, "name": destination.name})
            except Exception:
                for _, temp_path, destination in reversed(finalized):
                    if destination.is_file() and not temp_path.exists():
                        os.replace(destination, temp_path)
                for source, temp_path, _ in reversed(staged):
                    if temp_path.is_file() and not source.exists():
                        os.replace(temp_path, source)
                self._restore_media_indexes(index_snapshot)
                raise
            return {"renamed": renamed}

    def delete_source_media(self, project_id: str, relative_paths: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not isinstance(relative_paths, list) or not relative_paths or not all(isinstance(path, str) for path in relative_paths):
            raise ValidationError("paths must be a non-empty array of strings")
        normalized_paths = [path.replace("\\", "/") for path in relative_paths]
        if len({path.casefold() for path in normalized_paths}) != len(normalized_paths):
            raise ValidationError("paths cannot contain duplicate media items")
        with self._lock:
            resolved = [self._resolve_project_media_file(project_id, path, source_only=True) for path in normalized_paths]
            project_dir, media_root = resolved[0][0], resolved[0][1]
            sources = [item[2] for item in resolved]
            for source in sources:
                self._ensure_media_index_entry(project_dir, media_root, source)
            index_snapshot = self._snapshot_media_indexes(media_root)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            staging_root = media_root / f".milo-delete-{stamp}"
            counter = 1
            while staging_root.exists():
                staging_root = media_root / f".milo-delete-{stamp}-{counter}"
                counter += 1
            staging_root.mkdir()
            staged: list[tuple[Path, Path]] = []
            deleted = [
                {
                    "oldPath": source.relative_to(project_dir).as_posix(),
                    "path": None,
                    "name": source.name,
                }
                for source in sources
            ]
            try:
                for index, source in enumerate(sources, 1):
                    staged_path = staging_root / f"{index:06d}{source.suffix}"
                    os.replace(source, staged_path)
                    staged.append((source, staged_path))
                self._remove_media_index_paths(media_root, [item["oldPath"] for item in deleted])
            except Exception:
                for source, staged_path in reversed(staged):
                    if staged_path.is_file() and not source.exists():
                        source.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(staged_path, source)
                self._restore_media_indexes(index_snapshot)
                if staging_root.is_dir():
                    shutil.rmtree(staging_root, ignore_errors=True)
                raise
            shutil.rmtree(staging_root, ignore_errors=True)
            return {"deleted": deleted}

    def delete_source_folder(self, project_id: str, relative_folder: str) -> dict[str, Any]:
        with self._lock:
            project_dir, source_root, source = self._resolve_source_folder(project_id, relative_folder, must_exist=True)
            if source == source_root:
                raise ValidationError("The media/sources root cannot be deleted")
            media_root = (project_dir / "media").resolve()
            media_files: list[Path] = []
            for path in source.rglob("*"):
                if not path.is_file():
                    continue
                mime_type = mimetypes.guess_type(path.name)[0] or ""
                if not (mime_type.startswith("image/") or mime_type.startswith("audio/")):
                    continue
                resolved_path = path.resolve()
                if source_root not in resolved_path.parents:
                    raise ValidationError("The media file escapes media/sources")
                media_files.append(path)
            media_files.sort(key=lambda path: self._natural_name_key(path.relative_to(source).as_posix()))
            for path in media_files:
                self._ensure_media_index_entry(project_dir, media_root, path)
            index_snapshot = self._snapshot_media_indexes(media_root)
            metadata = self._read_source_folder_types(project_id)
            metadata_snapshot = deepcopy(metadata)
            old_prefix = source.relative_to(project_dir).as_posix()
            deleted = [
                {
                    "oldPath": path.relative_to(project_dir).as_posix(),
                    "path": None,
                    "name": path.name,
                }
                for path in media_files
            ]
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            staging_root = media_root / f".milo-delete-folder-{stamp}"
            counter = 1
            while staging_root.exists():
                staging_root = media_root / f".milo-delete-folder-{stamp}-{counter}"
                counter += 1
            staging_root.mkdir()
            staged_folder = staging_root / source.name
            moved = False
            try:
                os.replace(source, staged_folder)
                moved = True
                if deleted:
                    self._remove_media_index_paths(media_root, [item["oldPath"] for item in deleted])
                remaining_metadata = {
                    folder: types
                    for folder, types in metadata.items()
                    if folder != old_prefix and not folder.startswith(f"{old_prefix}/")
                }
                self._write_source_folder_types(project_id, remaining_metadata)
            except Exception:
                if moved and staged_folder.is_dir() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged_folder, source)
                self._restore_media_indexes(index_snapshot)
                self._write_source_folder_types(project_id, metadata_snapshot)
                if staging_root.is_dir():
                    shutil.rmtree(staging_root, ignore_errors=True)
                raise
            shutil.rmtree(staging_root, ignore_errors=True)
            return {
                "folder": {"oldPath": old_prefix, "path": None, "name": source.name},
                "deleted": deleted,
            }

    def import_source_media(
        self,
        project_id: str,
        filename: str,
        source: BinaryIO,
        folder: str | None = None,
    ) -> dict[str, Any]:
        clean_name = safe_media_name(Path(str(filename or "upload").replace("\\", "/")).name, label="filename")
        mime_type = mimetypes.guess_type(clean_name)[0] or ""
        if not (mime_type.startswith("image/") or mime_type.startswith("audio/")):
            raise ValidationError("Only image or audio media can be imported")
        normalized_folder = str(folder).replace("\\", "/").strip("/") if folder else ""
        if normalized_folder.startswith("media/sources"):
            project_dir, source_root, destination_dir = self._resolve_source_folder(project_id, normalized_folder)
            if destination_dir == source_root:
                source_root.mkdir(parents=True, exist_ok=True)
            elif not destination_dir.is_dir():
                raise NotFoundError(folder)
            relative_folder = destination_dir.relative_to(source_root).as_posix()
            relative_path = clean_name if relative_folder == "." else f"{relative_folder}/{clean_name}"
        else:
            if "/" in normalized_folder:
                raise ValidationError("folder must be media/sources or one of its subdirectories")
            kind_folder = "imported-images" if mime_type.startswith("image/") else "imported-audio"
            source_folder = safe_filename(folder) if folder else "imports"
            relative_path = f"{kind_folder}/{source_folder}/{clean_name}"
        result = self.import_image_source_file(project_id, relative_path, source, allow_audio=True)
        result["mimeType"] = mime_type
        return result

    def import_media(
        self,
        project_id: str,
        filename: str,
        source: BinaryIO,
        gallery: str | None = None,
    ) -> dict[str, Any]:
        clean_name = safe_filename(filename)
        gallery_name = safe_filename(gallery) if gallery else None
        mime_type = mimetypes.guess_type(clean_name)[0] or "application/octet-stream"
        media_root = self.project_dir(project_id) / "media"
        destination_dir = media_root / "timg" / "tb_xl" if mime_type == "image/jpeg" else media_root / "timg"
        destination_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{clean_name}.", suffix=".uploading", dir=destination_dir)
        digest = hashlib.sha1()
        size = 0
        with os.fdopen(fd, "wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
        suffix = {"image/jpeg": ".jpg", "audio/mpeg": ".mp3"}.get(mime_type, Path(clean_name).suffix.lower())
        final_name = f"{digest.hexdigest()}{suffix}"
        final_path = destination_dir / final_name
        if final_path.exists():
            stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            final_path = destination_dir / f"{digest.hexdigest()}.duplicate-{stamp}{suffix}"
        os.replace(temp_name, final_path)
        width = height = None
        if mime_type.startswith("image/") and final_path.exists():
            with Image.open(final_path) as image:
                width, height = image.size
        result = {
            "id": self._numeric_id(f"{digest.hexdigest()}:{clean_name}"),
            "name": clean_name,
            "hash": digest.hexdigest(),
            "size": size,
            "width": width,
            "height": height,
            "type": mime_type,
            "gallery": gallery_name,
            "path": str(final_path.relative_to(self.project_dir(project_id))).replace("\\", "/"),
        }
        index_path = media_root / "index.json"
        entries = self._read_json(index_path) if index_path.exists() else []
        entry = {key: result[key] for key in ("id", "name", "hash", "type", "path")}
        entry["kind"] = "gallery" if gallery_name else "file"
        entry["gallery"] = gallery_name
        entries.append(entry)
        self._atomic_json(index_path, entries)
        return result

    def import_image_source_file(self, project_id: str, relative_path: str, source: BinaryIO, *, allow_audio: bool = False) -> dict[str, Any]:
        """Import one browser-selected image while preserving its source folder."""
        self.get_project(project_id)
        raw_parts = str(relative_path or "").replace("\\", "/").split("/")
        if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
            raise ValidationError("Image source paths must include a filename and cannot escape the project directory")
        safe_parts = [safe_media_name(part, label="image source path component") for part in raw_parts]
        if any(not part for part in safe_parts):
            raise ValidationError("The image source path contains an invalid filename")
        mime_type = mimetypes.guess_type(safe_parts[-1])[0] or ""
        allowed = mime_type.startswith("image/") or (allow_audio and mime_type.startswith("audio/"))
        if not allowed:
            raise ValidationError("Image source files must use a supported image format" if not allow_audio else "Media must use an image or audio format")
        project_dir = self.project_dir(project_id).resolve()
        destination = project_dir.joinpath("media", "sources", *safe_parts)
        if project_dir not in destination.resolve().parents:
            raise ValidationError("The image source path escapes the project directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".uploading", dir=destination.parent)
        size = 0
        with os.fdopen(fd, "wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
        final_path = destination
        if final_path.exists():
            stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            final_path = destination.with_name(f"{destination.stem}.duplicate-{stamp}{destination.suffix}")
        os.replace(temp_name, final_path)
        return {
            "name": safe_parts[-1],
            "path": str(final_path.relative_to(project_dir)).replace("\\", "/"),
            "size": size,
        }

    def build_project(self, project_id: str) -> dict[str, Any]:
        """Validate and compile project sources, then atomically publish generated EOS."""
        if self.source_mode(project_id) != "milo-ir":
            raise ValidationError("Only milo-ir projects can be built from source")
        try:
            product = compile_project(self.project_dir(project_id))
        except MiloSourceError as exc:
            raise ValidationError(str(exc)) from exc
        saved = self.write_generated_script(project_id, product.script)
        return {
            "stage": "build",
            "built": True,
            "script": saved,
            "warnings": [warning.as_dict() for warning in product.warnings],
            "materializedFiles": list(product.materialized_files),
            "preview": f"/preview/{project_id}/",
        }

    @staticmethod
    def _migration_source_snapshot(project_dir: Path) -> dict[str, bytes]:
        paths = [project_dir / "outline.yaml", project_dir / "milo.yaml"]
        source_dir = project_dir / "src"
        if source_dir.is_dir():
            paths.extend(sorted(source_dir.glob("*.milo.yaml"), key=lambda path: path.name.casefold()))
        return {
            path.relative_to(project_dir).as_posix(): path.read_bytes()
            for path in paths if path.is_file()
        }

    def _restore_migration_sources(self, project_dir: Path, snapshot: dict[str, bytes]) -> None:
        active = [project_dir / "outline.yaml", project_dir / "milo.yaml"]
        source_dir = project_dir / "src"
        if source_dir.is_dir():
            active.extend(source_dir.glob("*.milo.yaml"))
        history_dir = project_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        for path in active:
            if not path.is_file():
                continue
            relative = path.relative_to(project_dir).as_posix()
            if relative in snapshot:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
            destination = history_dir / f"failed-migration-{digest}-{path.name}"
            index = 1
            while destination.exists():
                destination = history_dir / f"failed-migration-{digest}-{index}-{path.name}"
                index += 1
            os.replace(path, destination)
        for relative, content in snapshot.items():
            self._atomic_bytes(project_dir / relative, content)

    def migrate_project(self, project_id: str) -> dict[str, Any]:
        metadata = self.get_project(project_id)
        if self.source_mode(project_id) == "milo-ir":
            return {
                "outlineMigrated": False,
                "sourcesComplete": True,
                "missingScenes": [],
                "history": [],
                "warnings": [],
                "migrated": True,
                "alreadyMigrated": True,
                "sourceMode": "milo-ir",
                "preview": f"/preview/{project_id}/",
            }
        project_dir = self.project_dir(project_id)
        original_script = self.load_script(project_id)
        source_snapshot = self._migration_source_snapshot(project_dir)
        try:
            result = migrate_project_dir(project_dir, str(metadata.get("title") or project_id))
        except Exception:
            self._restore_migration_sources(project_dir, source_snapshot)
            raise
        result["sourceMode"] = self.source_mode(project_id)
        result["migrated"] = result["sourceMode"] == "milo-ir"
        if not result.get("sourcesComplete"):
            self._restore_migration_sources(project_dir, source_snapshot)
            return result
        try:
            product = compile_project(self.project_dir(project_id))
        except MiloSourceError as exc:
            result["warnings"].extend(issue.as_dict() for issue in exc.issues)
            self._restore_migration_sources(project_dir, source_snapshot)
            return result
        except Exception:
            self._restore_migration_sources(project_dir, source_snapshot)
            raise
        if result.get("equivalenceRequired") and product.script != original_script:
            result["warnings"].append({
                "level": "error",
                "code": "MIGRATION_EOS_NOT_EQUIVALENT",
                "message": "The YAML reconstruction is not deeply equivalent to the original eosscript.json; the project mode was not changed.",
                "path": "eosscript.json",
            })
            result["sourcesComplete"] = False
            self._restore_migration_sources(project_dir, source_snapshot)
            return result
        saved = self._write_script_version(project_id, product.script)
        with self._lock:
            current = self._read_json(self._metadata_path(project_id))
            current["sourceMode"] = "milo-ir"
            current["updatedAt"] = utc_now()
            self._atomic_json(self._metadata_path(project_id), current)
        result.update({
            "migrated": True,
            "sourceMode": "milo-ir",
            "script": saved,
            "preview": f"/preview/{project_id}/",
        })
        result["warnings"].extend(warning.as_dict() for warning in product.warnings)
        return result

    def media_upload_response(self, project_id: str, uploaded: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": uploaded["id"],
            "name": uploaded["name"],
            "mediaHash": {
                "id": self._numeric_id(uploaded["hash"]),
                "hash": uploaded["hash"],
                "size": uploaded["size"],
                "mimeType": uploaded["type"],
                "thumbnailLarge": f"/preview/{project_id}/media/{uploaded['hash']}?size=l",
                "dimensions": {"width": uploaded["width"], "height": uploaded["height"]},
            },
        }

    def archive_media(self, project_id: str, relative_path: str) -> dict[str, str]:
        with self._lock:
            project_dir, media_root, source = self._resolve_project_media_file(project_id, relative_path)
            self._ensure_media_index_entry(project_dir, media_root, source)
            index_snapshot = self._snapshot_media_indexes(media_root)
            archive = project_dir / "media" / "archive" / datetime.now().strftime("%Y%m%dT%H%M%S%fZ") / source.name
            archive.parent.mkdir(parents=True, exist_ok=True)
            old_path = source.relative_to(project_dir).as_posix()
            new_path = archive.relative_to(project_dir).as_posix()
            try:
                shutil.move(str(source), str(archive))
                self._rewrite_media_index_path(media_root, old_path, new_path)
            except Exception:
                if archive.is_file() and not source.exists():
                    os.replace(archive, source)
                self._restore_media_indexes(index_snapshot)
                raise
            return {"archived": new_path}

    def archive_media_ids(self, project_id: str, media_ids: list[int]) -> list[dict[str, str]]:
        wanted = {int(value) for value in media_ids}
        return [self.archive_media(project_id, record["path"]) for record in self._media_records(project_id) if int(record["id"]) in wanted]

    def _resolve_project_media_file(self, project_id: str, relative_path: str, *, source_only: bool = False) -> tuple[Path, Path, Path]:
        project_dir = self.project_dir(project_id).resolve()
        media_root = (project_dir / "media").resolve()
        source = (project_dir / relative_path).resolve()
        if media_root not in source.parents or not source.is_file() or source.name == "index.json":
            raise NotFoundError(relative_path)
        if "archive" in source.relative_to(media_root).parts:
            raise ValidationError("Archived media cannot be moved or renamed in the media library")
        source_root = (media_root / "sources").resolve()
        if source_only and source_root not in source.parents:
            raise ValidationError("The project media library can edit only author-owned media under media/sources")
        mime_type = mimetypes.guess_type(source.name)[0] or ""
        if not (mime_type.startswith("image/") or mime_type.startswith("audio/")):
            raise ValidationError("Only image and audio media can be moved or renamed")
        return project_dir, media_root, source

    @staticmethod
    def _resolve_media_folder(project_dir: Path, media_root: Path, relative_folder: str, *, source_only: bool = False) -> Path:
        normalized = str(relative_folder or "").replace("\\", "/").strip("/")
        parts = normalized.split("/") if normalized else []
        if not parts or parts[0] != "media" or any(part in {"", ".", ".."} for part in parts):
            raise ValidationError("The target folder must be a media/... path inside the current project")
        if len(parts) < 2 or parts[1] not in {"files", "galleries", "sources", "timg"}:
            raise ValidationError("The target folder must be under media/files, media/galleries, media/sources, or media/timg")
        if source_only and parts[1] != "sources":
            raise ValidationError("Project media can only be moved or copied within media/sources")
        destination = project_dir.joinpath(*parts).resolve()
        if media_root != destination and media_root not in destination.parents:
            raise ValidationError("The target folder escapes the current project's media directory")
        return destination

    def _rewrite_media_index_path(self, media_root: Path, old_path: str, new_path: str, display_name: str | None = None) -> None:
        old_normalized = old_path.replace("\\", "/")
        changed = False
        for index_path in media_root.rglob("index.json"):
            entries = self._read_json(index_path)
            if not isinstance(entries, list):
                continue
            index_changed = False
            for entry in entries:
                if isinstance(entry, dict) and entry.get("path") == old_normalized:
                    entry["path"] = new_path
                    if display_name is not None:
                        entry["name"] = display_name
                    index_changed = True
                    changed = True
            if index_changed:
                self._atomic_json(index_path, entries)
        if changed:
            return
        raise ValidationError(f"Path not found in the media index: {old_normalized}")

    def _remove_media_index_paths(self, media_root: Path, relative_paths: list[str]) -> None:
        wanted = {path.replace("\\", "/") for path in relative_paths}
        found: set[str] = set()
        for index_path in media_root.rglob("index.json"):
            entries = self._read_json(index_path)
            if not isinstance(entries, list):
                continue
            kept = []
            changed = False
            for entry in entries:
                path = entry.get("path") if isinstance(entry, dict) else None
                if path in wanted:
                    found.add(path)
                    changed = True
                else:
                    kept.append(entry)
            if changed:
                self._atomic_json(index_path, kept)
        missing = sorted(wanted - found)
        if missing:
            raise ValidationError(f"Path not found in the media index: {missing[0]}")

    def _ensure_media_index_entry(self, project_dir: Path, media_root: Path, source: Path) -> None:
        relative = source.relative_to(project_dir).as_posix()
        for index_path in media_root.rglob("index.json"):
            entries = self._read_json(index_path)
            if isinstance(entries, list) and any(isinstance(entry, dict) and entry.get("path") == relative for entry in entries):
                return
        canonical = media_root / "index.json"
        entries = self._read_json(canonical) if canonical.exists() else []
        if not isinstance(entries, list):
            entries = []
        digest = hashlib.sha1(source.read_bytes()).hexdigest()
        entries.append({
            "id": self._numeric_id(f"{digest}:{source.name}"),
            "name": source.name,
            "hash": digest,
            "type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
            "path": relative,
            "kind": "file",
        })
        self._atomic_json(canonical, entries)

    @staticmethod
    def _snapshot_media_indexes(media_root: Path) -> dict[Path, bytes]:
        return {path: path.read_bytes() for path in media_root.rglob("index.json") if path.is_file()}

    def _restore_media_indexes(self, snapshot: dict[Path, bytes]) -> None:
        for path, content in snapshot.items():
            self._atomic_bytes(path, content)

    def rename_media(self, project_id: str, relative_path: str, new_name: str, *, source_only: bool = False) -> dict[str, str]:
        with self._lock:
            project_dir, media_root, source = self._resolve_project_media_file(project_id, relative_path, source_only=source_only)
            clean_name = safe_media_name(new_name, label="filename")
            if Path(clean_name).suffix.casefold() != source.suffix.casefold():
                raise ValidationError("Renaming must preserve the original file extension")
            destination = source.with_name(clean_name)
            if destination != source and destination.exists():
                raise ValidationError("The target filename already exists")
            self._ensure_media_index_entry(project_dir, media_root, source)
            index_snapshot = self._snapshot_media_indexes(media_root)
            old_path = source.relative_to(project_dir).as_posix()
            new_path = destination.relative_to(project_dir).as_posix()
            try:
                if destination != source:
                    os.replace(source, destination)
                self._rewrite_media_index_path(media_root, old_path, new_path, clean_name)
            except Exception:
                if destination != source and destination.is_file() and not source.exists():
                    os.replace(destination, source)
                self._restore_media_indexes(index_snapshot)
                raise
            return {"oldPath": old_path, "path": new_path, "name": clean_name}

    def move_media(self, project_id: str, relative_paths: list[str], relative_folder: str, *, source_only: bool = False) -> dict[str, list[dict[str, str]]]:
        if not isinstance(relative_paths, list) or not relative_paths:
            raise ValidationError("Select at least one media item to move")
        with self._lock:
            project_dir = self.project_dir(project_id).resolve()
            media_root = (project_dir / "media").resolve()
            destination_dir = self._resolve_media_folder(project_dir, media_root, relative_folder, source_only=source_only)
            resolved: list[tuple[Path, Path, str]] = []
            destinations: set[Path] = set()
            for relative_path in relative_paths:
                _, _, source = self._resolve_project_media_file(project_id, relative_path, source_only=source_only)
                destination = (destination_dir / source.name).resolve()
                if media_root not in destination.parents:
                    raise ValidationError("The target file escapes the current project's media directory")
                if destination in destinations:
                    raise ValidationError(f"Multiple media items would move to the same file: {destination.name}")
                if destination != source and destination.exists():
                    raise ValidationError(f"Target file already exists: {destination.name}")
                destinations.add(destination)
                resolved.append((source, destination, source.relative_to(project_dir).as_posix()))

            for source, _, _ in resolved:
                self._ensure_media_index_entry(project_dir, media_root, source)
            index_snapshot = self._snapshot_media_indexes(media_root)
            destination_dir.mkdir(parents=True, exist_ok=True)
            moved_pairs: list[tuple[Path, Path]] = []
            moved: list[dict[str, str]] = []
            try:
                for source, destination, old_path in resolved:
                    if destination != source:
                        os.replace(source, destination)
                        moved_pairs.append((source, destination))
                    new_path = destination.relative_to(project_dir).as_posix()
                    self._rewrite_media_index_path(media_root, old_path, new_path)
                    moved.append({"oldPath": old_path, "path": new_path, "name": destination.name})
            except Exception:
                for source, destination in reversed(moved_pairs):
                    if destination.is_file() and not source.exists():
                        os.replace(destination, source)
                self._restore_media_indexes(index_snapshot)
                raise
            return {"moved": moved}

    @staticmethod
    def _copy_destination(destination_dir: Path, filename: str, reserved: set[Path]) -> Path:
        direct = destination_dir / filename
        if not direct.exists() and direct not in reserved:
            return direct
        source_name = Path(filename)
        counter = 1
        while True:
            suffix = " - Copy" if counter == 1 else f" - Copy ({counter})"
            candidate = destination_dir / f"{source_name.stem}{suffix}{source_name.suffix}"
            if not candidate.exists() and candidate not in reserved:
                return candidate
            counter += 1

    def copy_media(self, project_id: str, relative_paths: list[str], relative_folder: str) -> dict[str, list[dict[str, str]]]:
        if not isinstance(relative_paths, list) or not relative_paths:
            raise ValidationError("Select at least one media item to copy")
        unique_paths = list(dict.fromkeys(relative_paths))
        with self._lock:
            project_dir = self.project_dir(project_id).resolve()
            media_root = (project_dir / "media").resolve()
            destination_dir = self._resolve_media_folder(project_dir, media_root, relative_folder, source_only=True)
            resolved: list[tuple[Path, Path, str]] = []
            reserved: set[Path] = set()
            for relative_path in unique_paths:
                _, _, source = self._resolve_project_media_file(project_id, relative_path, source_only=True)
                destination = self._copy_destination(destination_dir, source.name, reserved).resolve()
                if media_root not in destination.parents:
                    raise ValidationError("The target file escapes the current project's media directory")
                reserved.add(destination)
                resolved.append((source, destination, source.relative_to(project_dir).as_posix()))

            for source, _, _ in resolved:
                self._ensure_media_index_entry(project_dir, media_root, source)
            index_snapshot = self._snapshot_media_indexes(media_root)
            destination_dir.mkdir(parents=True, exist_ok=True)
            created: list[Path] = []
            copied: list[dict[str, str]] = []
            temp_paths: list[Path] = []
            try:
                for source, destination, old_path in resolved:
                    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".copying", dir=destination_dir)
                    os.close(fd)
                    temp_path = Path(temp_name)
                    temp_paths.append(temp_path)
                    shutil.copy2(source, temp_path)
                    os.replace(temp_path, destination)
                    temp_paths.remove(temp_path)
                    created.append(destination)
                    self._ensure_media_index_entry(project_dir, media_root, destination)
                    copied.append({"oldPath": old_path, "path": destination.relative_to(project_dir).as_posix(), "name": destination.name})
            except Exception:
                for path in reversed(created):
                    if path.is_file():
                        path.unlink()
                for path in temp_paths:
                    if path.is_file():
                        path.unlink()
                self._restore_media_indexes(index_snapshot)
                raise
            return {"copied": copied}

    def rename_media_id(self, project_id: str, media_id: int, new_name: str) -> dict[str, str]:
        record = next((item for item in self._media_records(project_id) if int(item["id"]) == int(media_id)), None)
        if record is None:
            raise NotFoundError(str(media_id))
        return self.rename_media(project_id, record["path"], new_name)

    def resolve_locator(self, project_id: str, locator: str, media_type: str | None = None) -> Path:
        script = self.load_script(project_id)
        project_dir = self.project_dir(project_id)
        if locator.startswith("file:"):
            pattern = locator[5:]
            candidates = []
            for name, metadata in script.get("files", {}).items():
                if pattern == "*" or pattern == name:
                    ext = mimetypes.guess_extension(metadata.get("type", "")) or Path(name).suffix
                    subdir = Path("tb_xl") if metadata.get("type") == "image/jpeg" else Path()
                    candidates.extend((
                        project_dir / "media" / "timg" / subdir / f"{metadata.get('hash', '')}{ext}",
                        project_dir / "media" / "files" / f"{metadata.get('hash', '')}{ext}",
                        project_dir / "media" / "files" / name,
                    ))
            for candidate in candidates:
                if candidate.is_file() and (not media_type or (mimetypes.guess_type(candidate.name)[0] or "") == media_type):
                    return candidate
        if locator.startswith("gallery:"):
            gallery_id, _, image_id = locator[8:].partition("/")
            gallery = script.get("galleries", {}).get(gallery_id, {})
            images = gallery.get("images", [])
            if image_id and image_id != "*":
                images = [image for image in images if str(image.get("id")) == image_id]
            gallery_name = safe_filename(gallery.get("name", gallery_id))
            for image in images:
                for candidate in (
                    project_dir / "media" / "timg" / "tb_xl" / f"{image.get('hash', '')}.jpg",
                    project_dir / "media" / "galleries" / gallery_name / f"{image.get('hash', '')}.jpg",
                    project_dir / "media" / "galleries" / gallery_name / f"{image.get('id', '')}.jpg",
                ):
                    if candidate.is_file():
                        return candidate
        raise NotFoundError(locator)

    def clone_script(self, project_id: str) -> dict[str, Any]:
        return deepcopy(self.load_script(project_id))
