from __future__ import annotations

import copy
import math
import re
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

from .models import (
    Action,
    AssetDefinition,
    MiloSourceError,
    OutlineDocument,
    OutlineEdge,
    OutlineNode,
    Page,
    RuntimeDocument,
    SceneDocument,
    SourceBundle,
    SourceIssue,
)


ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,119}$")
STATE_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,119}$")
OUTLINE_KEYS = {"format", "title", "brief", "entry", "nodes"}
NODE_KEYS = {"name", "content", "next"}
EDGE_KEYS = {"to", "when", "priority"}
ASSET_KEYS = {"folder", "file", "locator", "pick", "recursive", "include", "exclude", "type"}
SCENE_KEYS = {"format", "scene", "entry", "pages"}
RUNTIME_META_KEYS = {"format", "state", "assets", "eos"}
KNOWN_EOS_ROOT_KEYS = {"files", "galleries", "modules", "init", "info"}
MAX_YAML_BYTES = 100_000_000
MAX_YAML_RECURSION_LIMIT = 20_000
_YAML_RECURSION_LOCK = threading.RLock()


class JsonSafeLoader(yaml.SafeLoader):
    """Safe YAML loader with JSON/YAML 1.2 scalar behavior."""


JsonSafeLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for first, resolvers in list(JsonSafeLoader.yaml_implicit_resolvers.items()):
    JsonSafeLoader.yaml_implicit_resolvers[first] = [
        (tag, regexp) for tag, regexp in resolvers
        if tag not in {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp"}
    ]
JsonSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


@contextmanager
def yaml_recursion_limit(required: int):
    """Temporarily raise Python's recursion limit for one guarded YAML operation."""

    with _YAML_RECURSION_LOCK:
        previous = sys.getrecursionlimit()
        target = min(MAX_YAML_RECURSION_LIMIT, max(previous, required))
        if target != previous:
            sys.setrecursionlimit(target)
        try:
            yield
        finally:
            if target != previous:
                sys.setrecursionlimit(previous)


def _error(code: str, message: str, path: str) -> MiloSourceError:
    return MiloSourceError([SourceIssue("error", code, message, path)])


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("TYPE_OBJECT", "Must be an object.", path)
    return value


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise _error("TYPE_STRING", "Must be a non-empty string.", path)
    return value.strip() if not allow_empty else value


def _check_id(value: Any, path: str, *, state: bool = False) -> str:
    result = _string(value, path)
    matcher = STATE_ID_RE if state else ID_RE
    if not matcher.fullmatch(result):
        raise _error("INVALID_ID", "IDs may contain only letters, digits, underscores, and hyphens, and must start with a letter or underscore.", path)
    return result


def _unknown_keys(value: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise _error("UNKNOWN_FIELD", f"Unsupported fields: {', '.join(unknown)}", path)


def load_yaml_text(text: str, label: str) -> Any:
    if not isinstance(text, str) or not text.strip():
        raise _error("EMPTY_SOURCE", "YAML cannot be empty.", label)
    if len(text.encode("utf-8")) > MAX_YAML_BYTES:
        raise _error("SOURCE_TOO_LARGE", "YAML exceeds the 100 MB limit.", label)
    max_indent = max(
        (len(line) - len(line.lstrip(" ")) for line in text.splitlines() if line.strip()),
        default=0,
    )
    required_recursion = 1_000 + max_indent * 4
    try:
        with yaml_recursion_limit(required_recursion):
            result = yaml.load(text, Loader=JsonSafeLoader)
    except yaml.YAMLError as exc:
        raise _error("INVALID_YAML", str(exc), label) from exc
    except RecursionError as exc:
        raise _error("SOURCE_TOO_DEEP", "YAML nesting depth exceeds the safety limit.", label) from exc
    _validate_json_value(result, label)
    return result


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _error("YAML_NON_JSON", "Numbers must be finite JSON numbers.", path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _error("YAML_KEY", "Object keys must be strings.", path)
            _validate_json_value(item, f"{path}.{key}")
        return
    raise _error("YAML_NON_JSON", "YAML may contain only JSON-representable values.", path)


def load_yaml_file(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise _error("SOURCE_MISSING", f"Missing source file {path.name}。", str(path)) from exc
    except UnicodeDecodeError as exc:
        raise _error("SOURCE_ENCODING", "Source files must be UTF-8.", str(path)) from exc
    return load_yaml_text(text, str(path))


def parse_outline(source: str | dict[str, Any], label: str = "outline.yaml") -> OutlineDocument:
    raw = load_yaml_text(source, label) if isinstance(source, str) else source
    if not isinstance(source, str):
        _validate_json_value(raw, label)
    data = _mapping(raw, label)
    _unknown_keys(data, OUTLINE_KEYS, label)
    if data.get("format") != "milo-outline":
        raise _error("OUTLINE_FORMAT", "format must be milo-outline.", f"{label}.format")
    title = _string(data.get("title"), f"{label}.title")
    entry = _check_id(data.get("entry"), f"{label}.entry")
    brief_value = data.get("brief")
    brief = _string(brief_value, f"{label}.brief") if brief_value is not None else ""

    nodes_raw = _mapping(data.get("nodes"), f"{label}.nodes")
    if not nodes_raw:
        raise _error("OUTLINE_NODES_EMPTY", "nodes must contain at least one node.", f"{label}.nodes")
    nodes: dict[str, OutlineNode] = {}
    for raw_id, raw_node in nodes_raw.items():
        node_id = _check_id(raw_id, f"{label}.nodes.<id>")
        node_data = _mapping(raw_node, f"{label}.nodes.{node_id}")
        _unknown_keys(node_data, NODE_KEYS, f"{label}.nodes.{node_id}")
        for required in ("name", "content", "next"):
            if required not in node_data:
                raise _error("OUTLINE_NODE_REQUIRED", f"Missing required field {required}。", f"{label}.nodes.{node_id}")
        next_raw = node_data.get("next")
        if not isinstance(next_raw, list):
            raise _error("OUTLINE_NEXT_TYPE", "next must be a list; use an empty list for terminal nodes.", f"{label}.nodes.{node_id}.next")
        edges: list[OutlineEdge] = []
        for index, raw_edge in enumerate(next_raw):
            edge_path = f"{label}.nodes.{node_id}.next[{index}]"
            edge = _mapping(raw_edge, edge_path)
            _unknown_keys(edge, EDGE_KEYS, edge_path)
            target = _check_id(edge.get("to"), f"{edge_path}.to")
            when = _string(edge.get("when", ""), f"{edge_path}.when", allow_empty=True).strip()
            priority = _string(edge.get("priority", "main"), f"{edge_path}.priority")
            edges.append(OutlineEdge(target, when, priority))
        nodes[node_id] = OutlineNode(
            node_id=node_id,
            name=_string(node_data.get("name"), f"{label}.nodes.{node_id}.name"),
            content=_string(node_data.get("content"), f"{label}.nodes.{node_id}.content"),
            next=tuple(edges),
        )
    return OutlineDocument(title=title, brief=brief, entry=entry, nodes=nodes)


def parse_runtime(source: str | dict[str, Any] | None, label: str = "milo.yaml") -> RuntimeDocument:
    raw = load_yaml_text(source, label) if isinstance(source, str) else (source or {})
    if not isinstance(source, str):
        _validate_json_value(raw, label)
    data = _mapping(raw, label)
    if data.get("format") not in {None, "milo-runtime"}:
        raise _error("RUNTIME_FORMAT", "If present, format must be milo-runtime.", f"{label}.format")
    if "pages" in data:
        raise _error("RUNTIME_PAGES", "pages must be defined in src/<node>.milo.yaml.", f"{label}.pages")
    escaped_eos = _mapping(data.get("eos") or {}, f"{label}.eos")
    if "pages" in escaped_eos:
        raise _error("RUNTIME_PAGES", "pages must be defined in src/<node>.milo.yaml.", f"{label}.eos.pages")
    state_raw = _mapping(data.get("state") or {}, f"{label}.state")
    state: dict[str, Any] = {}
    for raw_id, value in state_raw.items():
        state_id = _check_id(raw_id, f"{label}.state.<id>", state=True)
        if isinstance(value, (dict, list)):
            raise _error("STATE_SCALAR", "Initial state values must be strings, numbers, booleans, or null.", f"{label}.state.{state_id}")
        state[state_id] = value

    assets_raw = _mapping(data.get("assets") or {}, f"{label}.assets")
    assets: dict[str, AssetDefinition] = {}
    for raw_id, raw_asset in assets_raw.items():
        asset_id = _check_id(raw_id, f"{label}.assets.<id>")
        path = f"{label}.assets.{asset_id}"
        if isinstance(raw_asset, str):
            scalar_source = _string(raw_asset, path)
            if scalar_source.startswith(("file:", "gallery:")):
                assets[asset_id] = AssetDefinition(asset_id=asset_id, locator=scalar_source)
            else:
                assets[asset_id] = AssetDefinition(asset_id=asset_id, source=scalar_source)
            continue
        asset = _mapping(raw_asset, path)
        _unknown_keys(asset, ASSET_KEYS, path)
        sources = [key for key in ("folder", "file", "locator") if asset.get(key) is not None]
        if len(sources) != 1:
            raise _error("ASSET_SOURCE", "An asset must set exactly one of folder, file, or locator.", path)
        include = asset.get("include") or []
        exclude = asset.get("exclude") or []
        if not isinstance(include, list) or not all(isinstance(item, str) for item in include):
            raise _error("ASSET_FILTER", "include must be a list of strings.", f"{path}.include")
        if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
            raise _error("ASSET_FILTER", "exclude must be a list of strings.", f"{path}.exclude")
        recursive = asset.get("recursive", True)
        if not isinstance(recursive, bool):
            raise _error("ASSET_RECURSIVE", "recursive must be a boolean.", f"{path}.recursive")
        assets[asset_id] = AssetDefinition(
            asset_id=asset_id,
            folder=_string(asset["folder"], f"{path}.folder") if "folder" in asset else None,
            file=_string(asset["file"], f"{path}.file") if "file" in asset else None,
            locator=_string(asset["locator"], f"{path}.locator") if "locator" in asset else None,
            pick=_string(asset.get("pick", "sequence"), f"{path}.pick"),
            recursive=recursive,
            include=tuple(include),
            exclude=tuple(exclude),
            media_type=_string(asset["type"], f"{path}.type") if "type" in asset else None,
        )
    eos = dict(escaped_eos)
    for key, value in data.items():
        if key in RUNTIME_META_KEYS:
            continue
        if key in eos:
            raise _error("EOS_ROOT_DUPLICATE", f"Duplicate EOS top-level field: {key}", f"{label}.{key}")
        eos[key] = value
    for key in ("files", "galleries", "modules"):
        if key in eos and not isinstance(eos[key], dict):
            raise _error("EOS_ROOT_TYPE", f"{key} Must be an object.", f"{label}.{key}")
    if "init" in eos and not isinstance(eos["init"], str):
        raise _error("EOS_INIT_TYPE", "init must be a JavaScript string.", f"{label}.init")
    unknown_fields = tuple(sorted(set(eos) - KNOWN_EOS_ROOT_KEYS))
    return RuntimeDocument(state=state, assets=assets, eos=eos, unknown_fields=unknown_fields)


def parse_scene(source: str | dict[str, Any], label: str = "scene.milo.yaml", source_path: Path | None = None) -> SceneDocument:
    raw = load_yaml_text(source, label) if isinstance(source, str) else source
    if not isinstance(source, str):
        _validate_json_value(raw, label)
    data = _mapping(raw, label)
    _unknown_keys(data, SCENE_KEYS, label)
    if data.get("format") not in {None, "milo-ir"}:
        raise _error("SCENE_FORMAT", "If present, format must be milo-ir.", f"{label}.format")
    scene_id = _check_id(data.get("scene"), f"{label}.scene")
    entry = _string(data.get("entry"), f"{label}.entry")
    pages_raw = _mapping(data.get("pages"), f"{label}.pages")
    if not pages_raw:
        raise _error("SCENE_PAGES_EMPTY", "pages must contain at least one Page.", f"{label}.pages")
    pages: dict[str, Page] = {}
    for raw_id, raw_actions in pages_raw.items():
        page_id = _string(raw_id, f"{label}.pages.<id>")
        page_path = f"{label}.pages.{page_id}"
        if not isinstance(raw_actions, list):
            raise _error("PAGE_ACTIONS", "A Page must be a list of actions.", page_path)
        actions: list[Action] = []
        for index, raw_action in enumerate(raw_actions):
            action_path = f"{page_path}[{index}]"
            action = _mapping(raw_action, action_path)
            if len(action) != 1:
                raise _error("ACTION_SHAPE", "Each action must contain exactly one operation.", action_path)
            raw_kind, value = next(iter(action.items()))
            if not isinstance(raw_kind, str) or not raw_kind.strip():
                raise _error("ACTION_KIND", "An EOS command name must be a non-empty string.", action_path)
            actions.append(Action(kind=raw_kind, value=value, path=action_path))
        pages[page_id] = Page(page_id=page_id, actions=tuple(actions))
    return SceneDocument(scene_id=scene_id, entry=entry, pages=pages, source_path=source_path)


def load_project_sources(project_dir: Path) -> SourceBundle:
    project_dir = project_dir.resolve()
    outline = parse_outline(load_yaml_file(project_dir / "outline.yaml"), str(project_dir / "outline.yaml"))
    runtime_path = project_dir / "milo.yaml"
    runtime = parse_runtime(load_yaml_file(runtime_path), str(runtime_path))
    source_dir = project_dir / "src"
    if not source_dir.is_dir():
        raise _error("SOURCE_DIR_MISSING", "Missing src directory.", str(source_dir))
    scene_paths = sorted(source_dir.glob("*.milo.yaml"), key=lambda path: path.name.casefold())
    if not scene_paths:
        raise _error("SCENES_MISSING", "No *.milo.yaml files were found in src.", str(source_dir))
    scenes: dict[str, SceneDocument] = {}
    for path in scene_paths:
        scene = parse_scene(load_yaml_file(path), str(path), path)
        if scene.scene_id in scenes:
            raise _error("SCENE_DUPLICATE", f"Duplicate scene: {scene.scene_id}", str(path))
        expected_name = f"{scene.scene_id}.milo.yaml"
        if path.name != expected_name:
            raise _error("SCENE_FILENAME", f"Filename must be {expected_name}。", str(path))
        scenes[scene.scene_id] = scene
    return SourceBundle(outline=outline, runtime=runtime, scenes=scenes)
