from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .models import MiloSourceError, SourceIssue
from .parser import parse_outline, parse_runtime, parse_scene, yaml_recursion_limit


FAILURE_RE = re.compile(r"fail|failure|punish|lose|loss|失败|惩罚|放弃|退出", re.IGNORECASE)
CONTROL_ACTIONS = {"goto", "choice", "if", "random", "end"}


def _warning(code: str, message: str, path: str = "") -> SourceIssue:
    return SourceIssue("warning", code, message, path)


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_SOURCE_MISSING", f"Missing {path.name}", str(path))]) from exc
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_SOURCE_INVALID", f"Could not read {path.name}: {exc}", str(path))]) from exc


def _load_json(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON number: {value}")

    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except FileNotFoundError as exc:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_SOURCE_MISSING", f"Missing {path.name}", str(path))]) from exc
    except (UnicodeDecodeError, ValueError) as exc:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_SOURCE_INVALID", f"Could not read {path.name}: {exc}", str(path))]) from exc
    if not isinstance(value, dict) or not isinstance(value.get("pages"), dict) or not value["pages"]:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_EOS", "eosscript.json must contain a non-empty pages object.", str(path))])
    return value


def _json_depth(value: Any) -> int:
    maximum = 1
    stack: list[tuple[Any, int]] = [(value, 1)]
    expanded: set[int] = set()
    while stack:
        current, depth = stack.pop()
        maximum = max(maximum, depth)
        if not isinstance(current, (dict, list)):
            continue
        identity = id(current)
        if identity in expanded:
            continue
        expanded.add(identity)
        children = current.values() if isinstance(current, dict) else current
        stack.extend((child, depth + 1) for child in children)
    return maximum


def _dump_yaml(value: Any) -> str:
    required_recursion = 1_000 + _json_depth(value) * 8
    try:
        with yaml_recursion_limit(required_recursion):
            return yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=120)
    except RecursionError as exc:
        raise MiloSourceError([SourceIssue("error", "YAML_TOO_DEEP", "JSON nesting depth exceeds the safe YAML conversion limit.", "eosscript.json")]) from exc


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        raise


def _atomic_yaml(path: Path, value: Any) -> None:
    _atomic_text(path, _dump_yaml(value))


def _history_copy(project_dir: Path, source: Path, label: str) -> str:
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()[:12]
    destination = project_dir / "history" / f"{label}-{digest}{source.suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination.name


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return yaml.safe_dump(
            value,
            allow_unicode=True,
            sort_keys=True,
            default_flow_style=False,
            width=120,
        ).strip()
    return str(value).strip()


def _section(label: str, value: Any) -> str:
    if value is None:
        return f"{label}: null"
    text = _text(value)
    if not text:
        return ""
    return f"{label}:\n{text}" if isinstance(value, (dict, list)) or "\n" in text else f"{label}: {text}"


def _legacy_next(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        return [{"to": value}]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _edge_priority(target: str, when: str, non_fail_index: int) -> str:
    if FAILURE_RE.search(f"{target} {when}"):
        return "fail"
    return "main" if non_fail_index == 0 else "side"


def migrate_outline_05(raw: dict[str, Any]) -> tuple[dict[str, Any], list[SourceIssue]]:
    warnings: list[SourceIssue] = []
    raw_nodes = raw.get("nodes") if isinstance(raw.get("nodes"), dict) else {}
    if not raw_nodes:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_NODES", "The legacy Outline has no migratable nodes.", "outline.yaml.nodes")])
    raw_entry = raw.get("entry")
    entry = raw_entry if isinstance(raw_entry, str) and raw_entry in raw_nodes else next(iter(raw_nodes))
    if entry != raw_entry:
        warnings.append(_warning("MIGRATION_ENTRY", f"The legacy entry is invalid; selected the first node mechanically: {entry}。", "outline.yaml.entry"))

    excluded_brief_keys = {"format", "title", "entry", "nodes", "state"}
    preferred_brief_keys = ["premise", "direction", "mechanics", "characters", "media", "props"]
    remaining_brief_keys = sorted(set(raw) - excluded_brief_keys - set(preferred_brief_keys))
    brief_keys = [key for key in preferred_brief_keys if key in raw] + remaining_brief_keys
    brief_parts = [part for key in brief_keys if (part := _section(key, raw.get(key)))]

    migrated_nodes: dict[str, Any] = {}
    failure_edges: list[str] = []
    preferred_content_keys = [
        "goal", "experience", "content", "intensity", "media", "image_sources", "uses",
        "gameplay", "expand", "changes", "outcomes", "terminal", "review",
    ]
    for node_id, raw_node in raw_nodes.items():
        if not isinstance(node_id, str) or not isinstance(raw_node, dict):
            warnings.append(_warning("MIGRATION_NODE_SKIPPED", "The node ID or content is invalid and was not migrated.", f"outline.yaml.nodes.{node_id}"))
            continue
        name = _text(raw_node.get("title")) or node_id
        excluded_content_keys = {"title", "next"}
        remaining_content_keys = sorted(set(raw_node) - excluded_content_keys - set(preferred_content_keys))
        content_keys = [key for key in preferred_content_keys if key in raw_node] + remaining_content_keys
        content_parts = [part for key in content_keys if (part := _section(key, raw_node.get(key)))]
        content = "\n\n".join(content_parts)
        if not content:
            content = f'Preserve the graph position of node "{name}"; its actual content requires manual review'
            warnings.append(_warning("MIGRATION_CONTENT", "The node has no convertible content and was marked for review.", f"outline.yaml.nodes.{node_id}"))

        raw_edges = _legacy_next(raw_node.get("next"))
        edges: list[dict[str, str]] = []
        non_fail_index = 0
        for index, raw_edge in enumerate(raw_edges):
            target = raw_edge.get("to")
            if not isinstance(target, str) or target not in raw_nodes:
                warnings.append(_warning("MIGRATION_EDGE", f"Invalid exit target: {target}", f"outline.yaml.nodes.{node_id}.next[{index}]"))
                continue
            when = _text(raw_edge.get("when"))
            priority = raw_edge.get("priority") if raw_edge.get("priority") in {"main", "side", "fail"} else _edge_priority(target, when, non_fail_index)
            if priority != "fail":
                non_fail_index += 1
            edge: dict[str, str] = {"to": target, "priority": priority}
            if when:
                edge["when"] = when
            edges.append(edge)
            if priority == "fail":
                failure_edges.append(f"{node_id} → {target}: {when or 'failure route'}")
        migrated_nodes[node_id] = {"name": name, "content": content, "next": edges}

    if failure_edges:
        brief_parts.append(_section("failure_routes", failure_edges))
    brief = "\n\n".join(part for part in brief_parts if part)
    if not brief:
        brief = "The overall work direction requires manual review"
        warnings.append(_warning("MIGRATION_BRIEF", "No convertible work brief was found; it was marked for review.", "outline.yaml.brief"))
    return {
        "format": "milo-outline",
        "title": _text(raw.get("title")) or "Migrated Milo Project",
        "brief": brief,
        "entry": entry,
        "nodes": migrated_nodes,
    }, warnings


def _seed_outline(seed: Any, title: str) -> tuple[dict[str, Any], list[SourceIssue]]:
    premise = ""
    if isinstance(seed, dict):
        body = seed.get("outline_seed", seed)
        if isinstance(body, dict):
            premise = _text(body.get("concept")) or _text(body.get("premise")) or _text(body)
    content = premise or "The seed does not contain enough information; the work brief must be reviewed"
    return {
        "format": "milo-outline",
        "title": title,
        "brief": content,
        "entry": "opening",
        "nodes": {"opening": {"name": "Opening", "content": content, "next": []}},
    }, [_warning("MIGRATION_SEED_ONLY", "The project contains only a seed; a minimal Outline was generated and must be completed manually.", "outline_seed.yaml")]


def _state_and_assets(raw_outline: dict[str, Any], warnings: list[SourceIssue]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for state_id, raw_value in (raw_outline.get("state") or {}).items() if isinstance(raw_outline.get("state"), dict) else []:
        value = raw_value.get("initial") if isinstance(raw_value, dict) and "initial" in raw_value else raw_value
        if isinstance(value, (dict, list)):
            warnings.append(_warning("MIGRATION_STATE", "The initial state value is not scalar and was not migrated.", f"outline.yaml.state.{state_id}"))
            continue
        state[str(state_id)] = value
    assets: dict[str, Any] = {}
    nodes = raw_outline.get("nodes") if isinstance(raw_outline.get("nodes"), dict) else {}
    for node_id, node in nodes.items():
        for index, source in enumerate(node.get("image_sources") or []) if isinstance(node, dict) else []:
            if not isinstance(source, dict):
                continue
            asset_id = str(source.get("id") or f"{node_id}_images_{index + 1}")
            kind = source.get("kind")
            path = source.get("path")
            if kind not in {"local_folder", "local_file", "project_media"} or not isinstance(path, str):
                warnings.append(_warning("MIGRATION_ASSET", f"Image source {asset_id} could not be converted reliably; no asset was created.", f"outline.yaml.nodes.{node_id}.image_sources[{index}]"))
                continue
            field = "file" if kind == "local_file" else "folder"
            assets[asset_id] = {field: path, "pick": source.get("selection", "sequence"), "type": "image"}
    return {"format": "milo-runtime", "state": state, "assets": assets}


def _convert_scene_action(action: Any, path: str, warnings: list[SourceIssue]) -> dict[str, Any] | None:
    if not isinstance(action, dict):
        warnings.append(_warning("MIGRATION_SCENE_ACTION", "Scene action is not an object.", path))
        return None
    if "type" not in action and len(action) == 1:
        key = next(iter(action))
        return action if key in {"say", "image", "audio", "wait", "timer", "goto", "choice", "if", "random", "set", "prompt", "notification", "end"} else None
    kind = action.get("type")
    if kind == "say":
        text = action.get("text")
        return {"say": text} if isinstance(text, str) else None
    if kind == "image":
        source = action.get("source") if isinstance(action.get("source"), dict) else {}
        asset_id = source.get("media") or source.get("image_source")
        return {"image": f"{asset_id}/{action.get('pick', 'next')}"} if isinstance(asset_id, str) else None
    if kind in {"timer", "wait"}:
        duration = action.get("duration") or action.get("time")
        return {"wait": duration} if duration is not None else None
    if kind == "audio":
        asset_id = action.get("asset") or action.get("media")
        return {"audio": asset_id} if isinstance(asset_id, str) else None
    if kind == "goto" and isinstance(action.get("target"), str):
        return {"goto": action["target"]}
    if kind == "end":
        return {"end": True}
    warnings.append(_warning("MIGRATION_SCENE_ACTION", f"Scene action {kind} could not be converted reliably.", path))
    return None


def _convert_scene(raw: dict[str, Any], source_path: Path, warnings: list[SourceIssue]) -> dict[str, Any] | None:
    scene_id = raw.get("node") or raw.get("scene")
    entry = raw.get("entry")
    pages = raw.get("pages")
    if not isinstance(scene_id, str) or not isinstance(entry, str) or not isinstance(pages, dict):
        warnings.append(_warning("MIGRATION_SCENE", "Scene Source Missing node/entry/pages。", str(source_path)))
        return None
    output_pages: dict[str, list[dict[str, Any]]] = {}
    for page_id, raw_page in pages.items():
        page_path = f"{source_path}.pages.{page_id}"
        if isinstance(raw_page, list):
            raw_actions, next_value = raw_page, None
        elif isinstance(raw_page, dict):
            raw_actions, next_value = raw_page.get("actions"), raw_page.get("next")
        else:
            warnings.append(_warning("MIGRATION_SCENE_PAGE", "Page structure is invalid.", page_path))
            return None
        if not isinstance(raw_actions, list):
            warnings.append(_warning("MIGRATION_SCENE_PAGE", "Page Missing actions。", page_path))
            return None
        actions: list[dict[str, Any]] = []
        for index, action in enumerate(raw_actions):
            converted = _convert_scene_action(action, f"{page_path}.actions[{index}]", warnings)
            if converted is None:
                return None
            actions.append(converted)
        if not actions or next(iter(actions[-1])) not in CONTROL_ACTIONS:
            target = None
            if isinstance(next_value, str):
                target = next_value
            elif isinstance(next_value, dict):
                if isinstance(next_value.get("page"), str):
                    target = next_value["page"]
                elif isinstance(next_value.get("exit"), str):
                    target = "$" + next_value["exit"].lstrip("$")
            if target:
                actions.append({"goto": target})
        output_pages[str(page_id)] = actions
    return {"format": "milo-ir", "scene": scene_id, "entry": entry, "pages": output_pages}


def _eos_import_outline(project_dir: Path, title: str, warnings: list[SourceIssue], history: list[str]) -> dict[str, Any]:
    outline_path = project_dir / "outline.yaml"
    seed_path = project_dir / "outline_seed.yaml"
    brief = "The complete design and runtime content of the EOSScript."
    content = "This node contains all EOS Pages for the work."
    if outline_path.is_file():
        raw = _load_yaml(outline_path)
        if isinstance(raw, dict):
            try:
                existing = raw if raw.get("format") == "milo-outline" else migrate_outline_05(raw)[0]
                brief = _text(existing.get("brief")) or brief
                node_parts = []
                for node_id, node in (existing.get("nodes") or {}).items():
                    if isinstance(node, dict):
                        node_parts.append(f"{node.get('name') or node_id}:\n{_text(node.get('content'))}")
                content = "\n\n".join(node_parts) or content
            except MiloSourceError:
                warnings.append(_warning("MIGRATION_OUTLINE_CONTEXT", "The existing Outline could not be parsed; runtime content was still imported losslessly from EOSScript.", str(outline_path)))
        history.append(_history_copy(project_dir, outline_path, "outline-before-eos-import"))
    elif seed_path.is_file():
        seed = _load_yaml(seed_path)
        if isinstance(seed, dict):
            body = seed.get("outline_seed", seed)
            brief = _text(body.get("premise") if isinstance(body, dict) else body) or brief
        history.append(_history_copy(project_dir, seed_path, "outline-seed-legacy"))
    return {
        "format": "milo-outline",
        "title": title,
        "brief": brief,
        "entry": "main",
        "nodes": {"main": {"name": title, "content": content, "next": []}},
    }


def _default_eos_outline(title: str) -> dict[str, Any]:
    return {
        "format": "milo-outline",
        "title": title,
        "brief": "The complete experience and runtime behavior are defined by the imported EOSScript.",
        "entry": "main",
        "nodes": {
            "main": {
                "name": title,
                "content": "This node contains all EOS Pages and their runtime behavior.",
                "next": [],
            }
        },
    }


def _eosscript_documents(
    script: dict[str, Any],
    title: str,
    outline: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(script, dict):
        raise MiloSourceError([SourceIssue("error", "MIGRATION_EOS", "The EOSScript top level must be an object.", "eosscript.json")])
    pages = script.get("pages")
    if not isinstance(pages, dict) or not pages:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_EOS", "EOSScript must contain a non-empty pages object.", "eosscript.json.pages")])
    if "start" not in pages:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_EOS_START", "EOSScript must contain a start Page for lossless conversion.", "eosscript.json.pages.start")])

    runtime: dict[str, Any] = {"format": "milo-runtime", "state": {}, "assets": {}}
    escaped: dict[str, Any] = {}
    reserved = {"format", "state", "assets", "eos", "pages"}
    for key, value in script.items():
        if key == "pages":
            continue
        if key in reserved:
            escaped[key] = value
        else:
            runtime[key] = value
    if escaped:
        runtime["eos"] = escaped

    outline_document = outline if outline is not None else _default_eos_outline(title)
    scene = {"format": "milo-ir", "scene": "main", "entry": "start", "pages": pages}

    # Validate the exact documents before serialization. The same parsers are
    # used by Build after these values have been loaded from YAML text.
    required_recursion = 1_000 + _json_depth(script) * 8
    with yaml_recursion_limit(required_recursion):
        parse_outline(outline_document)
        parse_runtime(runtime)
        parse_scene(scene)
    return {
        "outline.yaml": outline_document,
        "milo.yaml": runtime,
        "src/main.milo.yaml": scene,
    }


def eosscript_to_milo_yaml(
    script: dict[str, Any],
    title: str = "Imported EOSScript",
    *,
    outline: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Convert a complete EOSScript JSON object into deterministic Milo YAML sources."""

    documents = _eosscript_documents(script, title.strip() or "Imported EOSScript", outline)
    return {path: _dump_yaml(value) for path, value in documents.items()}


def _migrate_eosscript(project_dir: Path, title: str) -> dict[str, Any]:
    script_path = project_dir / "eosscript.json"
    script = _load_json(script_path)
    warnings: list[SourceIssue] = []
    history = [_history_copy(project_dir, script_path, "eosscript-before-milo")]
    outline = _eos_import_outline(project_dir, title, warnings, history)

    sources = eosscript_to_milo_yaml(script, title, outline=outline)

    milo_path = project_dir / "milo.yaml"
    if milo_path.is_file():
        history.append(_history_copy(project_dir, milo_path, "milo-before-eos-import"))
    source_dir = project_dir / "src"
    if source_dir.is_dir():
        for source in sorted(source_dir.glob("*.milo.yaml"), key=lambda path: path.name.casefold()):
            history.append(_history_copy(project_dir, source, f"source-{source.stem}-before-eos-import"))
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
            archived = project_dir / "history" / f"inactive-{digest}-{source.name}"
            archived.parent.mkdir(parents=True, exist_ok=True)
            suffix = 2
            while archived.exists():
                archived = project_dir / "history" / f"inactive-{digest}-{suffix}-{source.name}"
                suffix += 1
            os.replace(source, archived)

    for relative_path, text in sources.items():
        _atomic_text(project_dir / relative_path, text)
    warnings.append(_warning("MIGRATION_EOS_IMPORTED", "EOSScript was imported as a complete YAML source.", "eosscript.json"))
    return {
        "outlineMigrated": True,
        "sourcesComplete": True,
        "missingScenes": [],
        "history": history,
        "warnings": [warning.as_dict() for warning in warnings],
        "equivalenceRequired": True,
    }


def migrate_project_dir(project_dir: Path, title: str) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    if (project_dir / "eosscript.json").is_file():
        return _migrate_eosscript(project_dir, title)
    outline_path = project_dir / "outline.yaml"
    seed_path = project_dir / "outline_seed.yaml"
    warnings: list[SourceIssue] = []
    history: list[str] = []
    raw_legacy: dict[str, Any] = {}

    if outline_path.is_file():
        raw = _load_yaml(outline_path)
        if not isinstance(raw, dict):
            raise MiloSourceError([SourceIssue("error", "MIGRATION_OUTLINE", "The outline.yaml top level must be an object.", str(outline_path))])
        if raw.get("format") == "milo-outline":
            migrated_outline = raw
            parse_outline(migrated_outline)
        else:
            raw_legacy = raw
            migrated_outline, outline_warnings = migrate_outline_05(raw)
            warnings.extend(outline_warnings)
            parse_outline(migrated_outline)
            history.append(_history_copy(project_dir, outline_path, "outline-legacy"))
            _atomic_yaml(outline_path, migrated_outline)
    elif seed_path.is_file():
        seed = _load_yaml(seed_path)
        migrated_outline, seed_warnings = _seed_outline(seed, title)
        warnings.extend(seed_warnings)
        parse_outline(migrated_outline)
        history.append(_history_copy(project_dir, seed_path, "outline-seed-legacy"))
        _atomic_yaml(outline_path, migrated_outline)
    else:
        raise MiloSourceError([SourceIssue("error", "MIGRATION_NO_DESIGN", "The project has neither outline.yaml nor outline_seed.yaml.", str(project_dir))])

    milo_path = project_dir / "milo.yaml"
    if not milo_path.exists():
        _atomic_yaml(milo_path, _state_and_assets(raw_legacy, warnings))

    scene_dir = project_dir / "scenes"
    source_dir = project_dir / "src"
    if scene_dir.is_dir():
        for scene_path in sorted(scene_dir.glob("*.yaml"), key=lambda path: path.name.casefold()):
            raw_scene = _load_yaml(scene_path)
            if not isinstance(raw_scene, dict):
                warnings.append(_warning("MIGRATION_SCENE", "The Scene Source top level is invalid.", str(scene_path)))
                continue
            converted = _convert_scene(raw_scene, scene_path, warnings)
            if converted is None:
                continue
            destination = source_dir / f"{converted['scene']}.milo.yaml"
            if not destination.exists():
                _atomic_yaml(destination, converted)

    node_ids = set((migrated_outline.get("nodes") or {}).keys())
    source_ids = {path.name[:-len(".milo.yaml")] for path in source_dir.glob("*.milo.yaml")} if source_dir.is_dir() else set()
    missing = sorted(node_ids - source_ids)
    for node_id in missing:
        warnings.append(_warning("MIGRATION_IR_MISSING", "The node has no convertible Scene Source; no speculative IR was created.", f"src/{node_id}.milo.yaml"))
    if seed_path.is_file() and "outline-seed-legacy" not in " ".join(history):
        history.append(_history_copy(project_dir, seed_path, "outline-seed-legacy"))
    return {
        "outlineMigrated": True,
        "sourcesComplete": not missing and bool(node_ids),
        "missingScenes": missing,
        "history": history,
        "warnings": [warning.as_dict() for warning in warnings],
    }
