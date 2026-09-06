"""MiloAIEditor local workflow bridge."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILL_ROOT.parents[1]
EDITOR_ROOT = Path(os.environ.get("MILO_EDITOR_ROOT", REPO_ROOT / "milo-editor")).resolve()
START_SCRIPT = EDITOR_ROOT / "start.ps1"
PROJECTS_ROOT = Path(os.environ.get("MILO_PROJECTS_ROOT", REPO_ROOT / "projects")).resolve()
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
NUMERIC_PROJECT_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))


class WorkflowError(RuntimeError):
    """A user-actionable local workflow error."""


def _endpoint(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _request(
    base_url: str,
    path: str,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
    timeout: float = 60.0,
) -> bytes:
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(_endpoint(base_url, path), data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise WorkflowError(f"{method} {path} failed ({exc.code}): {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise WorkflowError(f"Could not connect to editor service {base_url}: {exc.reason}") from exc


def _request_json(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    raw = _request(base_url, path, method, body, "application/json" if body is not None else None, timeout=timeout)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Editor returned invalid JSON: {path}") from exc


def _health(base_url: str) -> bool:
    try:
        data = _request_json(base_url, "/api/health")
    except WorkflowError:
        return False
    return bool(isinstance(data, dict) and data.get("ok"))


def _base_port(base_url: str) -> int:
    """Derive the listen port for a fresh editor instance from --base-url."""
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def ensure_editor(base_url: str, timeout: float, start: bool = True) -> bool:
    """Return whether this invocation started the local editor service."""
    if _health(base_url):
        return False
    if not start:
        raise WorkflowError(f"Editor service is not running: {base_url}")
    if not START_SCRIPT.is_file():
        raise WorkflowError(f"Editor start script not found: {START_SCRIPT}")

    port = str(_base_port(base_url))
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(START_SCRIPT), "-Port", port],
            cwd=EDITOR_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    else:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
            cwd=EDITOR_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _health(base_url):
            return True
        time.sleep(0.25)
    raise WorkflowError(f"Editor service startup timed out: {base_url}")


def _safe_project_id(value: str) -> str:
    if not PROJECT_ID_RE.fullmatch(value or ""):
        raise WorkflowError("project-id may contain only letters, digits, dots, underscores, and hyphens, with a maximum length of 80")
    return value


def _project_id(title: str, requested: str | None, existing_projects: Any = None) -> str:
    if requested:
        project_id = _safe_project_id(requested)
        existing_ids = {
            str(project.get("id"))
            for project in (existing_projects if isinstance(existing_projects, list) else [])
            if isinstance(project, dict) and project.get("id") is not None
        }
        if project_id.isdigit() or project_id in existing_ids:
            return project_id
        raise WorkflowError("A new project's project-id must be numeric; only existing legacy projects may continue using non-numeric IDs")
    numeric_ids = {
        int(project["id"])
        for project in (existing_projects if isinstance(existing_projects, list) else [])
        if isinstance(project, dict)
        and str(project.get("id", "")).isdigit()
        and int(project["id"]) > 0
    }
    candidate = max(numeric_ids, default=100000) + 1
    while candidate in numeric_ids:
        candidate += 1
    project_id = str(candidate)
    if not NUMERIC_PROJECT_ID_RE.fullmatch(project_id):
        raise WorkflowError("The automatically generated project-id is not a valid numeric ID")
    return project_id


def _read_text(path_value: str) -> str:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise WorkflowError(f"Input file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise WorkflowError(f"Input file is not UTF-8: {path}") from exc
    if not text.strip():
        raise WorkflowError(f"Input file is empty: {path}")
    return text


def _validate_outline(text: str) -> None:
    required = ("format: milo-outline", "entry:", "nodes:")
    missing = [item for item in required if item not in text]
    if missing:
        raise WorkflowError(f"Outline 1.0 is missing fields: {', '.join(missing)}")


def ensure_project(base_url: str, project_id: str, title: str, author: str, source_mode: str = "milo-ir") -> tuple[dict[str, Any], bool]:
    projects = _request_json(base_url, "/api/projects")
    if isinstance(projects, list):
        for project in projects:
            if isinstance(project, dict) and str(project.get("id")) == project_id:
                return project, False
    created = _request_json(
        base_url,
        "/api/projects",
        "POST",
        {"id": project_id, "title": title or project_id, "author": author or "Local Author", "sourceMode": source_mode},
    )
    if not isinstance(created, dict):
        raise WorkflowError("Editor did not return a valid project record")
    return created, True


def save_text(base_url: str, path: str, text: str) -> dict[str, Any]:
    raw = _request(base_url, path, "PUT", text.rstrip().encode("utf-8") + b"\n", "text/yaml; charset=utf-8")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Editor returned invalid JSON after saving: {path}") from exc
    if not isinstance(result, dict):
        raise WorkflowError(f"Editor returned an invalid result after saving: {path}")
    return result


def editor_url(base_url: str, project_id: str) -> str:
    encoded = urllib.parse.quote(project_id, safe="")
    return f"{base_url.rstrip('/')}/milo/tease-graph/{encoded}"


def preview_url(base_url: str, project_id: str) -> str:
    encoded = urllib.parse.quote(project_id, safe="")
    return f"{base_url.rstrip('/')}/preview/{encoded}/"


def open_url(url: str) -> None:
    try:
        import webbrowser

        if not webbrowser.open(url):
            raise WorkflowError(f"Could not open the browser automatically; open this URL manually: {url}")
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError(f"Could not open the browser automatically; open this URL manually: {url}") from exc


def run_new(args: argparse.Namespace) -> dict[str, Any]:
    started = ensure_editor(args.base_url, args.timeout, not args.no_start)
    existing_projects = _request_json(args.base_url, "/api/projects")
    project_id = _project_id(args.title, args.project_id, existing_projects)
    project, created = ensure_project(args.base_url, project_id, args.title, args.author, "milo-ir")
    if not created:
        raise WorkflowError(f"Project {project_id} already exists; new will not overwrite an existing project")
    outline_saved = False
    if args.outline_file:
        outline = _read_text(args.outline_file)
        _validate_outline(outline)
        encoded_id = urllib.parse.quote(project_id, safe="")
        save_text(args.base_url, f"/api/projects/{encoded_id}/outline", outline)
        outline_saved = True
    url = editor_url(args.base_url, project_id)
    if args.open:
        open_url(url)
    return {
        "project_id": project_id,
        "project_created": True,
        "server_started": started,
        "outline_saved": outline_saved,
        "workspace": f"projects/{project_id}",
        "editor_url": url,
        "project": project,
    }


def run_build(args: argparse.Namespace) -> dict[str, Any]:
    started = ensure_editor(args.base_url, args.timeout, not args.no_start)
    project_id = _safe_project_id(args.project_id)
    encoded_id = urllib.parse.quote(project_id, safe="")
    result = _request_json(args.base_url, f"/api/projects/{encoded_id}/build", "POST")
    url = preview_url(args.base_url, project_id)
    if args.open:
        open_url(url)
    return {
        "project_id": project_id,
        "server_started": started,
        "stage": "build",
        "workspace": f"projects/{project_id}",
        "preview_url": url,
        "built": result,
    }


def run_migrate(args: argparse.Namespace) -> dict[str, Any]:
    started = ensure_editor(args.base_url, args.timeout, not args.no_start)
    project_id = _safe_project_id(args.project_id)
    encoded_id = urllib.parse.quote(project_id, safe="")
    result = _request_json(args.base_url, f"/api/projects/{encoded_id}/migrate", "POST")
    return {
        "project_id": project_id,
        "server_started": started,
        "stage": "migrate",
        "workspace": f"projects/{project_id}",
        "editor_url": editor_url(args.base_url, project_id),
        "migration": result,
    }


def run_media_search(args: argparse.Namespace) -> dict[str, Any]:
    from app.media_sources import MediaSourceError, discover_candidates, discovery_url

    try:
        url = args.url or discovery_url(args.provider, args.query)
        return discover_candidates(url, args.limit)
    except MediaSourceError as exc:
        raise WorkflowError(str(exc)) from exc


def run_media_fetch(args: argparse.Namespace) -> dict[str, Any]:
    from app.media_sources import MediaSourceError, fetch_media_url

    try:
        return fetch_media_url(PROJECTS_ROOT, args.project_id, args.source_id, args.url, args.cookies)
    except MediaSourceError as exc:
        raise WorkflowError(str(exc)) from exc


def _add_common(parser: argparse.ArgumentParser, title_required: bool = False, project_required: bool = False) -> None:
    parser.add_argument("--project-id", required=project_required)
    parser.add_argument("--title", required=title_required)
    parser.add_argument("--author", default="Local Author")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON only for agent-friendly parsing")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MiloAIEditor project workflow bridge")
    commands = parser.add_subparsers(dest="command", required=True)

    new = commands.add_parser("new", help="Create a milo-ir project and minimal source files")
    _add_common(new, title_required=True)
    new.add_argument("--outline-file", help="Optional Outline 1.0 YAML file")
    new.add_argument("--open", action="store_true", help="Open Tease Graph")

    build = commands.add_parser("build", help="Build and validate eosscript.json from Outline + Milo IR")
    _add_common(build, project_required=True)
    build.add_argument("--open", action="store_true", help="Open Preview after a successful build")

    migrate = commands.add_parser("migrate", help="Non-destructively migrate legacy Outline / Scene Source files in a project")
    _add_common(migrate, project_required=True)

    media_search = commands.add_parser("media-search", help="Search or list candidate galleries with gallery-dl without downloading media")
    search_input = media_search.add_mutually_exclusive_group(required=True)
    search_input.add_argument("--url", help="PornPics/EroMe search, tag, category, or user URL; ImageFap folder/profile URL")
    search_input.add_argument("--query", help="PornPics or EroMe search query")
    media_search.add_argument("--provider", choices=("pornpics", "erome", "imagefap"), help="Use with --query")
    media_search.add_argument("--limit", type=int, default=20, help="Return at most 1-100 candidates")
    media_search.add_argument("--json", action="store_true", help="Output JSON only for agent-friendly parsing")

    media_fetch = commands.add_parser("media-fetch", help="Download a selected gallery into the project's media/sources directory")
    media_fetch.add_argument("--project-id", required=True)
    media_fetch.add_argument("--source-id", required=True, help="Asset name that can be referenced from milo.yaml")
    media_fetch.add_argument("--url", required=True, help="Selected gallery, album, folder, image, or profile URL")
    media_fetch.add_argument("--cookies", help="Optional Netscape cookies.txt; it is not written to the project manifest")
    media_fetch.add_argument("--json", action="store_true", help="Output JSON only for agent-friendly parsing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "new":
            result = run_new(args)
        elif args.command == "build":
            result = run_build(args)
        elif args.command == "migrate":
            result = run_migrate(args)
        elif args.command == "media-search":
            if args.query and not args.provider:
                raise WorkflowError("--query requires --provider pornpics or erome")
            if args.provider == "imagefap" and args.query:
                raise WorkflowError("For ImageFap, locate content on the site first, then use --url to list folder/profile candidates")
            result = run_media_search(args)
        elif args.command == "media-fetch":
            result = run_media_fetch(args)
        else:
            raise WorkflowError(f"Unknown command: {args.command}")
    except WorkflowError as exc:
        print(f"milo_workflow: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "build":
        warnings = result.get("built", {}).get("warnings", [])
        print(f"Project: {result['project_id']}")
        print(f"Build: successful; {len(warnings)} warning(s)")
        print(f"Preview: {result['preview_url']}")
    elif args.command == "migrate":
        migration = result.get("migration", {})
        print(f"Project: {result['project_id']}")
        print(f"Migration: {'switched to milo-ir' if migration.get('migrated') else 'partially completed; still legacy-eos'}")
        print(f"Warnings: {len(migration.get('warnings', []))}")
        print(f"Tease Graph: {result['editor_url']}")
    elif args.command == "media-search":
        print(f"Source: {result['source_url']}")
        print(f"Candidates: {len(result['candidates'])}")
        for candidate in result["candidates"]:
            print(candidate["url"])
    elif args.command == "media-fetch":
        print(f"Project: {result['project_id']}")
        print(f"Source: {result['source_url']}")
        print(f"Files: {result['file_count']}")
        print(f"Asset directory: {result['source_folder']}")
        print(f"Add to assets in milo.yaml: {json.dumps(result['asset_yaml'], ensure_ascii=False)}")
    else:
        print(f"Project: {result['project_id']}")
        print(f"Workspace: {result['workspace']}")
        print(f"Outline: {'saved supplied file' if result['outline_saved'] else 'created minimal template'}")
        print(f"Tease Graph: {result['editor_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
