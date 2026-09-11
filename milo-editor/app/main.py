from __future__ import annotations

import json
import html
import mimetypes
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .config import EDITOR_ROOT, MONACO_ROOT, RUNTIME_ROOT, TEASE_GRAPH_ROOT
from .graphql_api import GraphQLDispatcher
from .milo_ir import MiloSourceError
from .media_sources import MediaSourceError, fetch_media_url
from .milovana_browser import (
    MilovanaBrowserClient,
    MilovanaBrowserError,
    authenticated_browser_status,
    browser_runtime_status,
    launch_browser,
)
from .milovana_deploy import (
    MilovanaDeployCancelled,
    MilovanaDeployError,
    build_deploy_plan,
    deploy_project,
)
from .storage import NotFoundError, ProjectStore, StoreError


store = ProjectStore()
graphql = GraphQLDispatcher(store)
app = FastAPI(title="MiloAIEditor Local API", version="0.1.0")
deploy_jobs: dict[str, dict[str, Any]] = {}
deploy_cancel_events: dict[str, threading.Event] = {}


def _require_local_request(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Milovana Deploy can only be called from the local editor.")


def _safe_runtime_file(relative_path: str) -> Path:
    root = RUNTIME_ROOT.resolve()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=404)
    if not target.is_file():
        raise HTTPException(status_code=404)
    return target


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/eos/editor/teases")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "projects": len(store.list_projects()),
        "editorAssets": EDITOR_ROOT.exists(),
        "runtime": str(RUNTIME_ROOT),
        "runtimeAvailable": (RUNTIME_ROOT / "eos.html").is_file(),
    }


@app.post("/graphql/")
async def graphql_endpoint(request: Request) -> JSONResponse:
    payload = await request.json()
    if isinstance(payload, list):
        return JSONResponse([graphql.dispatch(item) for item in payload])
    return JSONResponse(graphql.dispatch(payload))


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    return store.list_projects()


@app.post("/api/projects")
async def create_project(request: Request) -> dict[str, Any]:
    body = await request.json()
    try:
        return store.create_project(
            body["id"],
            body.get("title") or body["id"],
            body.get("author") or "Local Author",
            body.get("script"),
            body.get("sourceMode", "legacy-eos"),
        )
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/script")
def get_script(project_id: str) -> dict[str, Any]:
    try:
        return store.load_script(project_id)
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/projects/{project_id}/script")
async def put_script(project_id: str, request: Request) -> dict[str, Any]:
    try:
        return store.save_script(project_id, await request.json())
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/galleries")
def list_project_galleries(project_id: str) -> list[dict[str, Any]]:
    try:
        return store.list_galleries(project_id)
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/outline")
def get_outline(project_id: str) -> Response:
    try:
        return Response(store.load_outline(project_id), media_type="text/yaml")
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/projects/{project_id}/outline")
async def put_outline(project_id: str, request: Request) -> dict[str, Any]:
    try:
        return store.save_outline(project_id, (await request.body()).decode("utf-8"))
    except (StoreError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/tease-graph-layout")
def get_tease_graph_layout(project_id: str) -> dict[str, Any]:
    try:
        return store.load_tease_graph_layout(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/projects/{project_id}/tease-graph-layout")
async def put_tease_graph_layout(project_id: str, request: Request) -> dict[str, Any]:
    try:
        return store.save_tease_graph_layout(project_id, await request.json())
    except (StoreError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/media")
def list_media(project_id: str, q: str = "") -> list[dict[str, Any]]:
    try:
        return store.list_source_media(project_id, q)
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media")
async def upload_media(
    project_id: str,
    upload: UploadFile = File(...),
    folder: str | None = Form(None),
    gallery: str | None = Form(None),
) -> dict[str, Any]:
    try:
        return store.import_source_media(project_id, upload.filename or "upload", upload.file, folder if folder is not None else gallery)
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/media/folders")
def list_media_folders(project_id: str) -> list[dict[str, Any]]:
    try:
        return store.list_source_folders(project_id)
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/folders")
async def create_media_folder(project_id: str, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("The request body must be a JSON object")
        if not isinstance(body.get("parent"), str) or not isinstance(body.get("name"), str) or not isinstance(body.get("mediaType"), str):
            raise ValueError("parent, name, and mediaType must be strings")
        return store.create_source_folder(project_id, body["parent"], body["name"], body["mediaType"])
    except (StoreError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/folders/rename")
async def rename_media_folder(project_id: str, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        folder = body.get("path", body.get("folder")) if isinstance(body, dict) else None
        if not isinstance(folder, str) or not isinstance(body.get("name"), str):
            raise ValueError("path (or folder) and name must be strings")
        return store.rename_source_folder(project_id, folder, body["name"])
    except (StoreError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/folders/delete")
async def delete_media_folder(project_id: str, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        folder = body.get("path") if isinstance(body, dict) else None
        if not isinstance(folder, str) or body.get("confirm") is not True:
            raise ValueError("path must be a string and confirm must be true")
        return store.delete_source_folder(project_id, folder)
    except (StoreError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/auto-rename")
async def auto_rename_media(project_id: str, request: Request) -> dict[str, list[dict[str, str]]]:
    try:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("paths"), list) or not all(isinstance(path, str) for path in body["paths"]):
            raise ValueError("paths must be an array of strings")
        prefix = body.get("prefix")
        if prefix is not None and not isinstance(prefix, str):
            raise ValueError("prefix must be a string")
        return store.auto_rename_source_media(project_id, body["paths"], prefix)
    except (StoreError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/delete")
async def delete_media(project_id: str, request: Request) -> dict[str, list[dict[str, Any]]]:
    try:
        body = await request.json()
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("paths"), list)
            or not all(isinstance(path, str) for path in body["paths"])
            or body.get("confirm") is not True
        ):
            raise ValueError("paths must be an array of strings and confirm must be true")
        return store.delete_source_media(project_id, body["paths"])
    except (StoreError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/url")
async def import_media_url(project_id: str, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("The request body must be a JSON object")
        source_id = body.get("sourceId")
        url = body.get("url")
        if not isinstance(source_id, str) or not isinstance(url, str):
            raise ValueError("sourceId and url must be strings")
        return await run_in_threadpool(fetch_media_url, store.root, project_id, source_id, url)
    except (MediaSourceError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/image-source-folder")
async def upload_image_source_folder(
    project_id: str,
    files: list[UploadFile] = File(...),
    paths: list[str] = Form(...),
) -> dict[str, Any]:
    if not files or len(files) != len(paths):
        raise HTTPException(status_code=400, detail="The number of image files does not match the number of relative paths")
    try:
        imported = [
            store.import_image_source_file(project_id, relative_path, upload.file)
            for upload, relative_path in zip(files, paths, strict=True)
        ]
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    folder = imported[0]["path"].split("/", 3)[:3]
    return {
        "path": "/".join(folder),
        "count": len(imported),
        "files": imported,
    }


@app.get("/api/projects/{project_id}/deploy/milovana/plan")
def milovana_deploy_plan(project_id: str, request: Request) -> dict[str, Any]:
    _require_local_request(request)
    try:
        project_dir = store.project_dir(project_id)
        plan = build_deploy_plan(project_id, project_dir)
        return {**plan.public_dict(), "projectTitle": str(store.get_project(project_id).get("title") or project_id), "browser": browser_runtime_status()}
    except (StoreError, MilovanaDeployError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/deploy/milovana/browser/open")
async def milovana_browser_open(request: Request) -> dict[str, Any]:
    _require_local_request(request)
    raw_body = await request.body()
    tease_id = ""
    if raw_body.strip():
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="The browser-open request body must be JSON.") from exc
        tease_id = str((body or {}).get("teaseId") or "").strip()
        if tease_id and not tease_id.isdigit():
            raise HTTPException(status_code=400, detail="teaseId must be numeric.")
    try:
        await run_in_threadpool(launch_browser)
        if tease_id:
            def focus() -> None:
                client = MilovanaBrowserClient()
                try:
                    client.focus_tease(tease_id)
                finally:
                    client.close()
            await run_in_threadpool(focus)
        return browser_runtime_status()
    except MilovanaBrowserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/deploy/milovana/browser/status")
async def milovana_browser_status(request: Request) -> dict[str, Any]:
    _require_local_request(request)
    return await run_in_threadpool(authenticated_browser_status)


@app.get("/api/deploy/milovana/teases")
async def milovana_teases(request: Request) -> dict[str, Any]:
    _require_local_request(request)

    def load() -> dict[str, Any]:
        client = MilovanaBrowserClient()
        try:
            return {"teases": client.list_eos_teases()}
        finally:
            client.close()

    try:
        return await run_in_threadpool(load)
    except MilovanaBrowserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/deploy/milovana/status")
def milovana_deploy_status(project_id: str, request: Request) -> dict[str, Any]:
    _require_local_request(request)
    status = deploy_jobs.get(project_id)
    if status is None:
        return {"phase": "idle", "running": False}
    return dict(status)


@app.post("/api/projects/{project_id}/deploy/milovana/stop")
def milovana_deploy_stop(project_id: str, request: Request) -> dict[str, Any]:
    _require_local_request(request)
    status = deploy_jobs.get(project_id)
    if not status or not status.get("running"):
        return {**(status or {"phase": "idle", "running": False}), "stopRequested": False}

    cancel_event = deploy_cancel_events.get(project_id)
    if cancel_event is None:
        cancel_event = threading.Event()
        deploy_cancel_events[project_id] = cancel_event
    cancel_event.set()
    updated = {
        **status,
        "phase": "stopping",
        "running": True,
        "stopRequested": True,
    }
    deploy_jobs[project_id] = updated
    return dict(updated)


@app.post("/api/projects/{project_id}/deploy/milovana")
async def milovana_deploy(project_id: str, request: Request) -> dict[str, Any]:
    _require_local_request(request)
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="The request body must be JSON.") from exc
    body = body or {}
    create_new = bool(body.get("createNew"))
    resume = bool(body.get("resume"))
    tease_id = str(body.get("teaseId") or "").strip()
    create_title: str | None = None
    if create_new:
        confirmations = body.get("confirmations") or {}
        required = ("terms", "responsibility", "adultsOnly")
        if not isinstance(confirmations, dict) or not all(confirmations.get(key) is True for key in required):
            raise HTTPException(
                status_code=400,
                detail="Before creating a new Milovana tease, you must explicitly accept the Terms, acknowledge upload responsibility, and confirm that all models and fictional characters are 18+.",
            )
        try:
            project = store.get_project(project_id)
        except StoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        create_title = str(body.get("title") or project.get("title") or project_id).strip()
        if not create_title:
            raise HTTPException(status_code=400, detail="A title is required to create a new Milovana tease.")
        tease_id = ""
    elif not tease_id.isdigit():
        raise HTTPException(status_code=400, detail="teaseId must be numeric, or choose to create a new tease.")
    current = deploy_jobs.get(project_id) or {}
    if current.get("running"):
        raise HTTPException(status_code=409, detail="This project is already being deployed.")
    try:
        project_dir = store.project_dir(project_id)
        build_deploy_plan(project_id, project_dir)
    except (StoreError, MilovanaDeployError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cancel_event = threading.Event()
    deploy_cancel_events[project_id] = cancel_event
    deploy_jobs[project_id] = {
        "phase": "starting",
        "running": True,
        "teaseId": tease_id or None,
        "createNew": create_new,
        "resume": resume,
        "completed": 0,
        "total": 0,
        "uploaded": 0,
        "reused": 0,
        "stopRequested": False,
    }

    def update_status(update: dict[str, Any]) -> None:
        previous = deploy_jobs.get(project_id) or {}
        phase = str(update.get("phase") or previous.get("phase") or "")
        if previous.get("stopRequested") and phase not in {"done", "failed", "stopped"}:
            phase = "stopping"
            update = {**update, "phase": phase}
        deploy_jobs[project_id] = {
            **previous,
            **update,
            "running": phase not in {"done", "failed", "stopped"},
        }

    try:
        result = await run_in_threadpool(
            deploy_project,
            project_id,
            project_dir,
            tease_id or None,
            create_title=create_title,
            progress=update_status,
            should_stop=cancel_event.is_set,
            resume=resume,
        )
    except MilovanaDeployCancelled as exc:
        update_status({"phase": "stopped", "error": str(exc), "stopRequested": True})
        return dict(deploy_jobs[project_id])
    except MilovanaDeployError as exc:
        update_status({"phase": "failed", "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        deploy_cancel_events.pop(project_id, None)
    return result


@app.post("/api/projects/{project_id}/build")
async def build_project(project_id: str, request: Request) -> dict[str, Any]:
    raw_body = await request.body()
    if raw_body.strip():
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="The build request body must be empty or an empty object") from exc
        if body != {}:
            raise HTTPException(status_code=400, detail="build does not accept an EOS script or other source payload; edit the project's Milo IR instead")
    try:
        return store.build_project(project_id)
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/migrate")
async def migrate_project(project_id: str, request: Request) -> dict[str, Any]:
    if (await request.body()).strip():
        raise HTTPException(status_code=400, detail="migrate does not accept a source payload; it only migrates files already present in the project")
    try:
        return store.migrate_project(project_id)
    except (StoreError, MiloSourceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/eos/upload.php")
async def eos_upload(
    id: str,
    Filedata: UploadFile = File(...),
    Filename: str | None = Form(None),
) -> dict[str, Any]:
    try:
        uploaded = store.import_media(id, Filename or Filedata.filename or "upload", Filedata.file)
        return store.media_upload_response(id, uploaded)
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/archive")
async def archive_media(project_id: str, request: Request) -> dict[str, str]:
    body = await request.json()
    try:
        return store.archive_media(project_id, body["path"])
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/rename")
async def rename_media(project_id: str, request: Request) -> dict[str, str]:
    try:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("path"), str) or not isinstance(body.get("name"), str):
            raise ValueError("path and name must be strings")
        return store.rename_media(project_id, body["path"], body["name"], source_only=True)
    except (StoreError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/move")
async def move_media(project_id: str, request: Request) -> dict[str, list[dict[str, str]]]:
    try:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("paths"), list) or not all(isinstance(path, str) for path in body["paths"]):
            raise ValueError("paths must be an array of strings")
        if not isinstance(body.get("folder"), str):
            raise ValueError("folder must be a string")
        return store.move_media(project_id, body["paths"], body["folder"], source_only=True)
    except (StoreError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/media/copy")
async def copy_media(project_id: str, request: Request) -> dict[str, list[dict[str, str]]]:
    try:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("paths"), list) or not all(isinstance(path, str) for path in body["paths"]):
            raise ValueError("paths must be an array of strings")
        if not isinstance(body.get("folder"), str):
            raise ValueError("folder must be a string")
        return store.copy_media(project_id, body["paths"], body["folder"])
    except (StoreError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/media/query.php")
def query_media(url: str, projectId: str = "estim-mafia-property", size: str = "l", type: str | None = None) -> dict[str, Any]:
    try:
        media_path = store.resolve_locator(projectId, url, type)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "url": f"/project-media/{projectId}/{media_path.relative_to(store.project_dir(projectId)).as_posix()}",
        "type": mimetypes.guess_type(media_path.name)[0] or "application/octet-stream",
        "size": size,
    }


@app.get("/project-media/{project_id}/{relative_path:path}")
def project_media(project_id: str, relative_path: str) -> FileResponse:
    project_root = store.project_dir(project_id).resolve()
    media_root = (project_root / "media").resolve()
    target = (project_root / relative_path).resolve()
    if media_root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target)


@app.get("/preview/{project_id}/")
def preview(project_id: str) -> HTMLResponse:
    try:
        project = store.get_project(project_id)
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    title = json.dumps(project.get("title", project_id))
    author = json.dumps(project.get("author", "Local Author"))
    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,height=device-height,initial-scale=1\">
<title>{html.escape(str(project.get('title', project_id)))}</title><link rel=\"stylesheet\" href=\"/runtime/eos.load.css\">
<script src=\"/runtime/script/jquery.min.js\"></script></head>
<body class=\"eosTopBody\"><iframe class=\"eosIframe\" src=\"/preview/{project_id}/eos.html\" allowfullscreen></iframe>
<script>window.MILO_PROJECT_ID={json.dumps(project_id)};window.MILO_TITLE={title};window.MILO_AUTHOR={author};</script>
<script src=\"/local-assets/preview.outer.js\"></script></body></html>""")


@app.get("/webteases/showtease.php")
def editor_preview_compat(id: str, page: str = "start") -> RedirectResponse:
    store.get_project(id)
    return RedirectResponse(f"/preview/{id}/?start={page}")


@app.get("/webteases/geteosscript.php")
def editor_script_compat(id: str) -> dict[str, Any]:
    return store.load_script(id)


@app.get("/preview/{project_id}/eos.html")
def preview_eos(project_id: str) -> HTMLResponse:
    store.get_project(project_id)
    source = _safe_runtime_file("eos.html").read_text(encoding="utf-8")
    for prefix in ("acorn-safe.min.js", "interpreter.min.js", "eos.load.css", "static/"):
        source = source.replace(f'"{prefix}', f'"/runtime/{prefix}').replace(f"'{prefix}", f"'/runtime/{prefix}")
    media_bridge = fr"""<script>
(function () {{
  var nativeFetch = window.fetch;
  window.fetch = function (input, init) {{
    var url = typeof input === 'string' ? input : input.url;
    var match = /^https:\/\/media\.milovana\.com\/timg\/(?:tb_([^/]+)\/)?([a-f0-9]{{40}})\.([a-z0-9]+)/i.exec(url);
    if (match) {{
      url = '/preview/{project_id}/media/' + match[2] + '?size=' + encodeURIComponent(match[1] || '') + '&ext=' + encodeURIComponent(match[3]);
      input = typeof input === 'string' ? url : new Request(url, input);
    }}
    return nativeFetch.call(this, input, init);
  }};
}})();
</script>"""
    source = source.replace("</head>", media_bridge + "</head>")
    return HTMLResponse(source)


@app.get("/preview/{project_id}/media/{digest}")
def preview_media(project_id: str, digest: str, size: str = "", ext: str = "") -> FileResponse:
    if not re.fullmatch(r"[A-Fa-f0-9]{40}", digest):
        raise HTTPException(status_code=404)
    packaged_root = store.project_dir(project_id) / "media" / "timg"
    candidates: list[Path] = []
    if ext.casefold() in {"jpg", "jpeg"}:
        candidates.extend((packaged_root / f"tb_{size}" / f"{digest}.jpg", packaged_root / "tb_xl" / f"{digest}.jpg"))
    candidates.extend((packaged_root / f"{digest}.{ext}", packaged_root / f"{digest}.mp3"))
    for candidate in candidates:
        if candidate.is_file():
            return FileResponse(candidate)
    # Generated image sequences already use content-addressed paths. Checking
    # those paths first avoids recursively scanning thousands of frame files
    # for every image request. Keep the indexed lookup as a compatibility
    # fallback for imported media stored in other layouts.
    local = store.find_media_by_hash(project_id, digest)
    if local is not None:
        return FileResponse(store.project_dir(project_id) / local["path"])
    raise HTTPException(status_code=404)


@app.get("/preview/{project_id}/eosscript.json")
def preview_script(project_id: str) -> dict[str, Any]:
    return store.load_script(project_id)


@app.get("/preview/{project_id}/config.ini")
def preview_config(project_id: str) -> Response:
    project = store.get_project(project_id)
    return Response(f"title={project.get('title', project_id)}\nauthor={project.get('author', 'Local Author')}\npreview=true\n", media_type="text/plain")


@app.get("/preview/{project_id}/static/{relative_path:path}")
def preview_dynamic_asset(project_id: str, relative_path: str) -> FileResponse:
    store.get_project(project_id)
    return FileResponse(_safe_runtime_file(f"static/{relative_path}"))


@app.get("/preview/{project_id}/timg/{relative_path:path}")
def preview_packaged_media(project_id: str, relative_path: str) -> FileResponse:
    store.get_project(project_id)
    project_root = (store.project_dir(project_id) / "media" / "timg").resolve()
    target = (project_root / relative_path).resolve()
    if project_root in target.parents and target.is_file():
        return FileResponse(target)
    digest = Path(relative_path).stem
    local = store.find_media_by_hash(project_id, digest)
    if local is not None:
        return FileResponse(store.project_dir(project_id) / local["path"])
    raise HTTPException(status_code=404)


@app.get("/runtime/{relative_path:path}")
def runtime_asset(relative_path: str) -> FileResponse:
    return FileResponse(_safe_runtime_file(relative_path))


@app.get("/local-assets/preview.outer.js")
def preview_outer() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parents[1] / "local-assets" / "preview.outer.js", media_type="application/javascript")


@app.get("/local-assets/editor.integration.js")
def editor_integration() -> FileResponse:
    path = Path(__file__).resolve().parents[1] / "local-assets" / "editor.integration.js"
    return FileResponse(
        path,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/milo/tease-graph/{project_id}")
def tease_graph(project_id: str) -> FileResponse:
    try:
        store.get_project(project_id)
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = TEASE_GRAPH_ROOT / "standalone.html"
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Tease Graph has not been built")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.get("/eos/editor/vendor/monaco/vs/{relative_path:path}")
def monaco_asset(relative_path: str) -> FileResponse:
    root = MONACO_ROOT.resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target)


@app.get("/eos/editor/{path:path}")
def editor(path: str) -> Response:
    # The captured EOS editor only accepts numeric tease ids. Milo projects may
    # use stable slug ids (for example, tease-20260802-094224); sending those
    # through the legacy shell makes its GraphQL client coerce the id to NaN
    # and leaves the page stuck at “Loading tease...”. Route such projects to
    # the maintained Milo outline editor instead of exposing that failure.
    segments = [part for part in path.strip("/").split("/") if part]
    if len(segments) >= 2 and segments[-1] == "edit" and not segments[0].isdigit():
        project_id = segments[0]
        try:
            project = store.get_project(project_id)
        except StoreError:
            pass
        else:
            migrated_to = project.get("migratedTo")
            if isinstance(migrated_to, str) and migrated_to.isdigit():
                try:
                    store.get_project(migrated_to)
                except StoreError:
                    pass
                else:
                    encoded = quote(migrated_to, safe="")
                    return RedirectResponse(f"/eos/editor/{encoded}/edit")
            encoded = quote(project_id, safe="")
            return RedirectResponse(f"/milo/tease-graph/{encoded}?project={encoded}")

    requested = (EDITOR_ROOT / path).resolve()
    if EDITOR_ROOT.resolve() in requested.parents and requested.is_file():
        return FileResponse(requested)
    index = EDITOR_ROOT / "index.html"
    if index.is_file():
        source = index.read_text(encoding="utf-8")
        integration_path = Path(__file__).resolve().parents[1] / "local-assets" / "editor.integration.js"
        version = integration_path.stat().st_mtime_ns if integration_path.is_file() else 0
        integration = f'<script src="/local-assets/editor.integration.js?v={version}"></script>'
        return HTMLResponse(
            source.replace("</body>", integration + "</body>"),
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    return HTMLResponse("<h1>EOS Editor assets have not been captured yet.</h1>", status_code=503)
