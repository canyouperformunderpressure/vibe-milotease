from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - urllib fallback remains supported
    curl_requests = None

from .config import REPO_ROOT
from .milovana_browser import MilovanaBrowserClient, MilovanaBrowserError


MILOVANA_ORIGIN = "https://milovana.com"
GRAPHQL_URL = f"{MILOVANA_ORIGIN}/graphql/"
UPLOAD_URL = f"{MILOVANA_ORIGIN}/api/eos/upload.php"
DEFAULT_AUTH_FILE = Path(os.environ.get("MILOVANA_AUTH_FILE", REPO_ROOT / "milo-test.json")).resolve()
MEDIA_HASH_BATCH_SIZE = max(1, int(os.environ.get("MILOVANA_MEDIA_HASH_BATCH_SIZE", "20")))
CHECKPOINT_FLUSH_EVERY = max(1, int(os.environ.get("MILOVANA_CHECKPOINT_FLUSH_EVERY", "10")))

CREATE_TEASE = """
mutation CreateTease($title: String!) {
  createTease(title: $title, type: EOS) {
    __typename
    id
    title
  }
}
"""

CHECK_MEDIA_HASH = """
query checkMediaHash($hash: String!) {
  mediaByHash(hash: $hash) {
    id
    mimeType
    size
    dimensions { width height }
  }
}
"""

ADD_FILE_TO_TEASE = """
mutation addFileToTease($teaseId: ID!, $hash: String!, $name: String!) {
  addFileToTease(teaseId: $teaseId, hash: $hash, name: $name) {
    id
    name
    mediaHash {
      id
      hash
      size
      mimeType
      dimensions { width height }
    }
  }
}
"""

VALIDATE_SCRIPT = """
query validateScript($teaseId: ID!, $script: String) {
  validateEosScript(teaseId: $teaseId, script: $script) {
    validationErrors { property message }
  }
}
"""

SAVE_SCRIPT = """
mutation SaveScript($teaseId: ID!, $script: String!) {
  saveEosScript(teaseId: $teaseId, script: $script) {
    tease { id }
  }
}
"""


class MilovanaDeployError(RuntimeError):
    pass


class MilovanaDeployCancelled(MilovanaDeployError):
    """Raised when the user explicitly asks an active Deploy to stop."""

    pass


@dataclass(frozen=True)
class AuthContext:
    headers: dict[str, str]
    source: str
    kind: str


@dataclass(frozen=True)
class DeployMedia:
    digest: str
    name: str
    path: Path
    mime_type: str
    size: int
    category: str


@dataclass(frozen=True)
class DeployPlan:
    project_id: str
    script_path: Path
    media: tuple[DeployMedia, ...]
    total_bytes: int
    image_count: int
    audio_count: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "mediaCount": len(self.media),
            "imageCount": self.image_count,
            "audioCount": self.audio_count,
            "totalBytes": self.total_bytes,
            "missingLocal": [],
        }


def _deploy_checkpoint_path(project_dir: Path, tease_id: str) -> Path:
    return project_dir.resolve() / ".milovana-deploy" / f"{tease_id}.json"


def _deploy_media_key(media: DeployMedia) -> str:
    # Include the logical remote name as well as the content hash. Reusing the
    # same bytes under a different EOS file/gallery name may still require a
    # distinct attachment operation on the tease.
    return f"{media.digest}\0{media.name}"


def _canonical_script_hash(script_text: str) -> str:
    try:
        parsed = json.loads(script_text)
    except json.JSONDecodeError:
        normalized = script_text
    else:
        normalized = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _script_media_hashes(script_text: str) -> set[str]:
    try:
        script = json.loads(script_text)
    except json.JSONDecodeError:
        return set()
    if not isinstance(script, dict):
        return set()
    hashes: set[str] = set()
    for record in (script.get("files") or {}).values():
        if isinstance(record, dict):
            digest = str(record.get("hash") or "")
            if len(digest) == 40:
                hashes.add(digest)
    for gallery in (script.get("galleries") or {}).values():
        if not isinstance(gallery, dict):
            continue
        for image in gallery.get("images") or []:
            if isinstance(image, dict):
                digest = str(image.get("hash") or "")
                if len(digest) == 40:
                    hashes.add(digest)
    return hashes


def _load_deploy_checkpoint(
    project_id: str,
    project_dir: Path,
    tease_id: str,
) -> tuple[set[str], str | None]:
    path = _deploy_checkpoint_path(project_dir, tease_id)
    if not path.is_file():
        return set(), None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set(), None
    if not isinstance(payload, dict):
        return set(), None
    if str(payload.get("projectId") or "") != project_id or str(payload.get("teaseId") or "") != tease_id:
        return set(), None
    completed = payload.get("completed")
    if not isinstance(completed, list):
        return set(), None
    script_hash = str(payload.get("remoteScriptHash") or "") or None
    return {str(item) for item in completed if isinstance(item, str)}, script_hash


def _save_deploy_checkpoint(
    project_id: str,
    project_dir: Path,
    tease_id: str,
    completed: set[str],
    *,
    remote_script_hash: str | None = None,
) -> None:
    path = _deploy_checkpoint_path(project_dir, tease_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "projectId": project_id,
        "teaseId": tease_id,
        "completed": sorted(completed),
        "remoteScriptHash": remote_script_hash,
    }
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def seed_deploy_checkpoint_prefix(
    project_id: str,
    project_dir: Path,
    tease_id: str,
    completed_count: int,
) -> int:
    """Record the already-completed prefix of an in-flight legacy Deploy.

    This is primarily a migration bridge for Deploy jobs that began before
    persistent checkpoints existed. The media plan is deterministic, so the
    first ``completed_count`` entries are exactly the entries already handled
    by that worker.
    """
    plan = build_deploy_plan(project_id, project_dir)
    checkpoint, script_hash = _load_deploy_checkpoint(project_id, project_dir, tease_id)
    if not script_hash:
        # Legacy workers already save the validated script before entering the
        # media loop, so their completed prefix belongs to the current local
        # remote-script representation.
        script_hash = _canonical_script_hash(prepare_remote_script(project_id, plan.script_path))
    for media in plan.media[: max(0, min(int(completed_count), len(plan.media)))]:
        checkpoint.add(_deploy_media_key(media))
    _save_deploy_checkpoint(
        project_id,
        project_dir,
        tease_id,
        checkpoint,
        remote_script_hash=script_hash,
    )
    return len(checkpoint)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _remote_gallery_id(project_id: str, gallery_id: str) -> str:
    """Return a Milovana-compatible stable UUID for a local gallery ID."""
    if _is_uuid(gallery_id):
        return gallery_id
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"milo:{project_id}:gallery:{gallery_id}"))


def _rewrite_gallery_references(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_rewrite_gallery_references(item, mapping) for item in value]
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, item in value.items():
            if key == "galleryId" and isinstance(item, str) and item in mapping:
                rewritten[key] = mapping[item]
            else:
                rewritten[key] = _rewrite_gallery_references(item, mapping)
        return rewritten
    if isinstance(value, str):
        for local_id, remote_id in mapping.items():
            prefix = f"gallery:{local_id}/"
            if value.startswith(prefix):
                return f"gallery:{remote_id}/{value[len(prefix):]}"
    return value


def prepare_remote_script(project_id: str, script_path: Path) -> str:
    """Convert local-friendly EOS metadata into Milovana's Restore schema."""
    try:
        script = json.loads(script_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MilovanaDeployError("eosscript.json could not be read.") from exc
    if not isinstance(script, dict):
        raise MilovanaDeployError("The top level of eosscript.json must be an object.")

    galleries = script.get("galleries") or {}
    if not isinstance(galleries, dict):
        raise MilovanaDeployError("eosscript.json galleries must be an object.")

    mapping = {
        str(gallery_id): _remote_gallery_id(project_id, str(gallery_id))
        for gallery_id in galleries
    }
    script = _rewrite_gallery_references(script, mapping)
    # Milo may carry local/editor metadata that the Milovana Restore schema does
    # not allow at the script root. Keep it in the local build, but never send it.
    script.pop("info", None)
    script["galleries"] = {
        mapping[str(gallery_id)]: gallery
        for gallery_id, gallery in galleries.items()
    }
    return json.dumps(script, ensure_ascii=False, separators=(",", ":"))


def _walk_auth(value: Any, candidates: list[tuple[str, Any]], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            folded = str(key).casefold().replace("-", "_")
            if folded in {
                "authorization", "token", "access_token", "accesstoken", "bearer_token",
                "bearertoken", "cookie", "cookies", "headers", "storage_state", "storagestate",
            }:
                candidates.append((folded, item))
            if isinstance(item, (dict, list)):
                _walk_auth(item, candidates, depth + 1)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                _walk_auth(item, candidates, depth + 1)


def _cookie_header(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        pairs = [f"{key}={item}" for key, item in value.items() if isinstance(item, (str, int, float))]
        return "; ".join(pairs) or None
    if isinstance(value, list):
        pairs: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "")
            if domain and "milovana.com" not in domain.casefold():
                continue
            name = item.get("name")
            cookie_value = item.get("value")
            if isinstance(name, str) and isinstance(cookie_value, str):
                pairs.append(f"{name}={cookie_value}")
        return "; ".join(pairs) or None
    return None


def load_auth_context(path: Path = DEFAULT_AUTH_FILE) -> AuthContext:
    path = path.resolve()
    if not path.is_file():
        raise MilovanaDeployError(f"Milovana authentication file does not exist: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MilovanaDeployError("The Milovana authentication file is not valid JSON.") from exc

    # Browser cookie-export extensions commonly write a bare list of cookie objects.
    top_level_cookie = _cookie_header(data) if isinstance(data, list) else None
    if top_level_cookie:
        return AuthContext(headers={"Cookie": top_level_cookie}, source=path.name, kind="cookie")

    candidates: list[tuple[str, Any]] = []
    _walk_auth(data, candidates)
    headers: dict[str, str] = {}

    # Explicit headers are the strongest signal and support exported request/session JSON.
    for key, value in candidates:
        if key == "headers" and isinstance(value, dict):
            for header_name, header_value in value.items():
                if isinstance(header_name, str) and isinstance(header_value, str):
                    lower = header_name.casefold()
                    if lower in {"authorization", "cookie"}:
                        headers[header_name] = header_value
            if headers:
                return AuthContext(headers=headers, source=path.name, kind="headers")

    for key, value in candidates:
        if key in {"cookie", "cookies", "storage_state", "storagestate"}:
            cookie = _cookie_header(value)
            if cookie:
                return AuthContext(headers={"Cookie": cookie}, source=path.name, kind="cookie")

    for key, value in candidates:
        if key == "authorization" and isinstance(value, str) and value.strip():
            return AuthContext(headers={"Authorization": value.strip()}, source=path.name, kind="authorization")

    for key, value in candidates:
        if key in {"token", "access_token", "accesstoken", "bearer_token", "bearertoken"} and isinstance(value, str) and value.strip():
            token = value.strip()
            if token.casefold().startswith(("bearer ", "basic ")):
                authorization = token
            else:
                authorization = f"Bearer {token}"
            return AuthContext(headers={"Authorization": authorization}, source=path.name, kind="token")

    # Common Playwright storageState format can be nested under arbitrary keys.
    if isinstance(data, dict):
        cookie = _cookie_header(data.get("cookies"))
        if cookie:
            return AuthContext(headers={"Cookie": cookie}, source=path.name, kind="cookie")

    raise MilovanaDeployError(
        "Could not identify a Milovana session in the authentication JSON. Supported forms include cookies/Playwright storageState, Authorization, or token fields."
    )


def auth_status(path: Path = DEFAULT_AUTH_FILE) -> dict[str, Any]:
    if not path.is_file():
        return {"available": False, "source": path.name, "recognized": False}
    try:
        auth = load_auth_context(path)
    except MilovanaDeployError:
        return {"available": True, "source": path.name, "recognized": False}
    result = {"available": True, "source": auth.source, "recognized": True, "kind": auth.kind}
    if auth.kind in {"cookie", "headers"}:
        cookie_header = next((value for key, value in auth.headers.items() if key.casefold() == "cookie"), "")
        result["cloudflareClearance"] = "cf_clearance=" in cookie_header
    return result


def _find_hash_file(root: Path, digest: str, preferred: str) -> Path | None:
    direct = root / preferred
    if direct.is_file():
        return direct
    matches = [path for path in root.glob(f"{digest}.*") if path.is_file()]
    return matches[0] if len(matches) == 1 else None


def build_deploy_plan(project_id: str, project_dir: Path) -> DeployPlan:
    project_dir = project_dir.resolve()
    script_path = project_dir / "eosscript.json"
    if not script_path.is_file():
        raise MilovanaDeployError("The project has no eosscript.json yet; run Build first.")
    try:
        script = json.loads(script_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MilovanaDeployError("eosscript.json could not be read.") from exc

    by_hash: dict[str, DeployMedia] = {}
    missing: list[str] = []

    for name, record in (script.get("files") or {}).items():
        if not isinstance(record, dict):
            continue
        digest = str(record.get("hash") or "")
        if len(digest) != 40:
            continue
        mime_type = str(record.get("type") or "application/octet-stream")
        extension = mimetypes.guess_extension(mime_type) or Path(str(name)).suffix or ".bin"
        path = _find_hash_file(project_dir / "media" / "files", digest, f"{digest}{extension}")
        if path is None:
            missing.append(str(name))
            continue
        size = path.stat().st_size
        by_hash.setdefault(digest, DeployMedia(digest, str(name), path, mime_type, size, "audio"))

    for gallery_id, gallery in (script.get("galleries") or {}).items():
        if not isinstance(gallery, dict):
            continue
        for image in gallery.get("images") or []:
            if not isinstance(image, dict):
                continue
            digest = str(image.get("hash") or "")
            if len(digest) != 40:
                continue
            path = _find_hash_file(project_dir / "media" / "timg" / "tb_xl", digest, f"{digest}.jpg")
            if path is None:
                # Legacy/materialized projects sometimes store directly under timg.
                path = _find_hash_file(project_dir / "media" / "timg", digest, f"{digest}.jpg")
            if path is None:
                missing.append(f"{gallery_id}/{image.get('id', digest)}")
                continue
            size = path.stat().st_size
            name = f"{gallery_id}-{image.get('id', digest)}.jpg"
            by_hash.setdefault(digest, DeployMedia(digest, name, path, "image/jpeg", size, "image"))

    if missing:
        preview = ", ".join(missing[:5])
        suffix = "…" if len(missing) > 5 else ""
        raise MilovanaDeployError(f"There are {len(missing)} media hashes with no local file: {preview}{suffix}")

    media = tuple(by_hash.values())
    return DeployPlan(
        project_id=project_id,
        script_path=script_path,
        media=media,
        total_bytes=sum(item.size for item in media),
        image_count=sum(item.category == "image" for item in media),
        audio_count=sum(item.category == "audio" for item in media),
    )


class MilovanaClient:
    def __init__(self, auth: AuthContext, timeout: float = 90.0):
        self.auth = auth
        self.timeout = timeout
        self.session = curl_requests.Session(impersonate="chrome") if curl_requests is not None else None

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Origin": MILOVANA_ORIGIN,
            "Referer": f"{MILOVANA_ORIGIN}/eos/editor/",
            **self.auth.headers,
        }
        if self.session is None:
            headers.setdefault("User-Agent", "Mozilla/5.0")
        if extra:
            headers.update(extra)
        return headers

    def _urllib_request(self, request: urllib.request.Request) -> bytes:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise MilovanaDeployError(f"Milovana HTTP {exc.code}: {body or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise MilovanaDeployError(f"Could not connect to Milovana: {exc.reason}") from exc

    @staticmethod
    def _raise_http_error(status_code: int, text: str) -> None:
        preview = (text or "").replace("\n", " ")[:500]
        if status_code == 403 and "Just a moment" in preview:
            raise MilovanaDeployError(
                "Milovana was blocked by a Cloudflare 403. Open milovana.com normally in a browser and complete verification, then "
                "re-export the complete .milovana.com cookies including cf_clearance to milo-test.json."
            )
        raise MilovanaDeployError(f"Milovana HTTP {status_code}: {preview or 'request failed'}")

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.session is not None:
            try:
                response = self.session.post(
                    url,
                    headers=self._headers({"Content-Type": "application/json"}),
                    json=payload,
                    timeout=self.timeout,
                )
            except Exception as exc:  # curl_cffi exposes several transport exception subclasses
                raise MilovanaDeployError(f"Could not connect to Milovana: {exc}") from exc
            if response.status_code >= 400:
                self._raise_http_error(response.status_code, response.text)
            try:
                return response.json()
            except Exception as exc:
                raise MilovanaDeployError("Milovana returned unparseable JSON.") from exc

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, headers=self._headers({"Content-Type": "application/json"}), method="POST"
        )
        raw = self._urllib_request(request)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MilovanaDeployError("Milovana returned unparseable JSON.") from exc

    def graphql(self, query: str, variables: dict[str, Any], operation_name: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query, "variables": variables}
        if operation_name:
            payload["operationName"] = operation_name
        result = self._post_json(GRAPHQL_URL, payload)
        if result.get("errors"):
            message = "; ".join(str(item.get("message") or item) for item in result["errors"][:3])
            raise MilovanaDeployError(f"Milovana GraphQL error: {message}")
        return result.get("data") or {}

    def create_tease(self, title: str) -> str:
        clean_title = str(title or "").strip()
        if not clean_title:
            raise MilovanaDeployError("A title is required to create a new Milovana tease.")
        data = self.graphql(CREATE_TEASE, {"title": clean_title}, "CreateTease")
        result = data.get("createTease")
        tease_id = str((result or {}).get("id") or "") if isinstance(result, dict) else ""
        if not tease_id.isdigit():
            raise MilovanaDeployError("Milovana did not return a valid new tease ID.")
        return tease_id

    def media_by_hash(self, digest: str) -> dict[str, Any] | None:
        data = self.graphql(CHECK_MEDIA_HASH, {"hash": digest}, "checkMediaHash")
        media = data.get("mediaByHash")
        return media if isinstance(media, dict) else None

    def add_existing_media(self, tease_id: str, media: DeployMedia) -> dict[str, Any]:
        data = self.graphql(
            ADD_FILE_TO_TEASE,
            {"teaseId": tease_id, "hash": media.digest, "name": media.name},
            "addFileToTease",
        )
        result = data.get("addFileToTease")
        if not isinstance(result, dict):
            raise MilovanaDeployError(f"Existing media {media.name} could not be attached to the tease.")
        return result

    def upload_media(self, tease_id: str, media: DeployMedia) -> dict[str, Any]:
        url = f"{UPLOAD_URL}?{urllib.parse.urlencode({'id': tease_id})}"
        if self.session is not None:
            try:
                with media.path.open("rb") as source:
                    response = self.session.post(
                        url,
                        headers=self._headers(),
                        data={"Filename": media.name},
                        files={"Filedata": (media.name, source, media.mime_type)},
                        timeout=self.timeout,
                    )
            except Exception as exc:
                raise MilovanaDeployError(f"Could not connect to Milovana while uploading {media.name}: {exc}") from exc
            if response.status_code >= 400:
                self._raise_http_error(response.status_code, response.text)
            try:
                result = response.json()
            except Exception as exc:
                raise MilovanaDeployError(f"Uploading {media.name} returned invalid JSON from Milovana.") from exc
        else:
            boundary = "----MiloDeployFallbackBoundary"
            file_bytes = media.path.read_bytes()
            parts = [
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"Filename\"\r\n\r\n{media.name}\r\n".encode(),
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"Filedata\"; filename=\"{media.name}\"\r\nContent-Type: {media.mime_type}\r\n\r\n".encode(),
                file_bytes,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
            request = urllib.request.Request(
                url,
                data=b"".join(parts),
                headers=self._headers({"Content-Type": f"multipart/form-data; boundary={boundary}"}),
                method="POST",
            )
            raw = self._urllib_request(request)
            try:
                result = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MilovanaDeployError(f"Uploading {media.name} returned invalid JSON from Milovana.") from exc
        if isinstance(result, dict) and (result.get("error") or result.get("errors")):
            raise MilovanaDeployError(f"Uploading {media.name} failed: {result.get('error') or result.get('errors')}")
        if not isinstance(result, dict):
            raise MilovanaDeployError(f"Uploading {media.name} returned an unexpected response format.")
        return result

    def validate_script(self, tease_id: str, script_text: str) -> list[dict[str, Any]]:
        data = self.graphql(
            VALIDATE_SCRIPT,
            {"teaseId": tease_id, "script": script_text},
            "validateScript",
        )
        validation = data.get("validateEosScript") or {}
        errors = validation.get("validationErrors") or []
        return [item for item in errors if isinstance(item, dict)]

    def save_script(self, tease_id: str, script_text: str) -> None:
        data = self.graphql(
            SAVE_SCRIPT,
            {"teaseId": tease_id, "script": script_text},
            "SaveScript",
        )
        saved = data.get("saveEosScript")
        if not isinstance(saved, dict):
            raise MilovanaDeployError("Milovana did not confirm that saveEosScript succeeded.")


def deploy_project(
    project_id: str,
    project_dir: Path,
    tease_id: str | None,
    *,
    create_title: str | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    resume: bool = False,
    client_factory: Callable[[], Any] = MilovanaBrowserClient,
) -> dict[str, Any]:
    plan = build_deploy_plan(project_id, project_dir)
    report = progress or (lambda _update: None)
    stop_requested = should_stop or (lambda: False)

    def check_stop() -> None:
        if stop_requested():
            raise MilovanaDeployCancelled("Deploy was stopped by the user.")

    check_stop()
    client = client_factory()

    try:
        check_stop()
        require_authenticated = getattr(client, "require_authenticated", None)

        resolved_tease_id = str(tease_id or "").strip()
        if not resolved_tease_id:
            if not create_title:
                raise MilovanaDeployError("A Milovana tease ID is required, or choose to create a new tease.")
            if callable(require_authenticated):
                require_authenticated()
            check_stop()
            report({"phase": "create", "title": create_title})
            resolved_tease_id = client.create_tease(create_title)
            report({"phase": "created", "teaseId": resolved_tease_id, "title": create_title})
        elif not resolved_tease_id.isdigit():
            raise MilovanaDeployError("Milovana tease ID must be numeric.")
        tease_id = resolved_tease_id

        focus_tease = getattr(client, "focus_tease", None)
        if callable(focus_tease):
            focus_tease(tease_id)

        script_text = prepare_remote_script(project_id, plan.script_path)
        current_script_hash = _canonical_script_hash(script_text)
        check_stop()
        checkpoint, checkpoint_script_hash = _load_deploy_checkpoint(project_id, project_dir, tease_id)
        resume_media_only = bool(
            resume
            and checkpoint_script_hash == current_script_hash
        )
        if not resume_media_only and callable(require_authenticated):
            require_authenticated()

        remote_changed = False
        if checkpoint and not resume_media_only:
            load_script = getattr(client, "load_script", None)
            if callable(load_script):
                remote_script_text = load_script(tease_id)
                remote_script_hash = _canonical_script_hash(remote_script_text)
                remote_changed = remote_script_hash != checkpoint_script_hash
                if remote_changed:
                    remote_media_hashes = _script_media_hashes(remote_script_text)
                    checkpoint = {
                        _deploy_media_key(media)
                        for media in plan.media
                        if _deploy_media_key(media) in checkpoint and media.digest in remote_media_hashes
                    }
            else:
                # A client that cannot inspect the remote script cannot safely
                # prove that checkpointed media still exist after web edits.
                remote_changed = True
                checkpoint.clear()
        checkpoint_keys = {_deploy_media_key(media) for media in plan.media}
        # Drop records for media that no longer exist in the current project.
        # This keeps update deployments small without letting the checkpoint
        # grow forever as assets are replaced.
        checkpoint.intersection_update(checkpoint_keys)
        skipped = sum(_deploy_media_key(media) in checkpoint for media in plan.media)
        total = len(plan.media)

        # A repeat Deploy with an unchanged remote script and a complete media
        # checkpoint has nothing to do. Avoid another validate/save round trip.
        if (
            bool(checkpoint)
            and skipped == total
            and checkpoint_script_hash == current_script_hash
            and not remote_changed
        ):
            result = {
                "ok": True,
                "projectId": project_id,
                "teaseId": tease_id,
                "mediaCount": total,
                "uploaded": 0,
                "reused": 0,
                "skipped": skipped,
                "totalBytes": plan.total_bytes,
                "noOp": True,
                "editorUrl": f"{MILOVANA_ORIGIN}/eos/editor/{tease_id}/edit",
                "backupUrl": f"{MILOVANA_ORIGIN}/eos/editor/{tease_id}/backup",
            }
            report({"phase": "done", **result})
            return result

        if not resume_media_only:
            report({
                "phase": "validate",
                "completed": skipped,
                "total": total,
                "uploaded": 0,
                "reused": 0,
                "skipped": skipped,
                "remoteChanged": remote_changed,
            })
            validation_errors = client.validate_script(tease_id, script_text)
            if validation_errors:
                summary = "; ".join(
                    f"{item.get('property', '?')}: {item.get('message', 'validation error')}"
                    for item in validation_errors[:5]
                )
                raise MilovanaDeployError(f"Milovana rejected Restore: {summary}")

            check_stop()
            report({
                "phase": "save",
                "completed": skipped,
                "total": len(plan.media),
                "uploaded": 0,
                "reused": 0,
                "skipped": skipped,
                "remoteChanged": remote_changed,
            })
            client.save_script(tease_id, script_text)
            _save_deploy_checkpoint(
                project_id,
                project_dir,
                tease_id,
                checkpoint,
                remote_script_hash=current_script_hash,
            )

        uploaded = 0
        reused = 0
        completed = skipped
        report({
            "phase": "media",
            "completed": completed,
            "total": total,
            "uploaded": 0,
            "reused": 0,
            "skipped": skipped,
            "remoteChanged": remote_changed,
            "resuming": resume_media_only,
        })

        pending = [media for media in plan.media if _deploy_media_key(media) not in checkpoint]
        existing_by_hash: dict[str, dict[str, Any] | None] = {}
        batch_lookup = None if resume_media_only else getattr(client, "media_by_hashes", None)
        if callable(batch_lookup):
            for start in range(0, len(pending), MEDIA_HASH_BATCH_SIZE):
                check_stop()
                chunk = pending[start : start + MEDIA_HASH_BATCH_SIZE]
                resolved = batch_lookup([media.digest for media in chunk])
                if not isinstance(resolved, dict):
                    raise MilovanaDeployError("Milovana returned an invalid batch media lookup response.")
                existing_by_hash.update(resolved)

        dirty_since_flush = 0

        def flush_checkpoint() -> None:
            nonlocal dirty_since_flush
            if dirty_since_flush <= 0:
                return
            _save_deploy_checkpoint(
                project_id,
                project_dir,
                tease_id,
                checkpoint,
                remote_script_hash=current_script_hash,
            )
            dirty_since_flush = 0

        try:
            for media in pending:
                check_stop()
                if resume_media_only:
                    existing = None
                elif callable(batch_lookup):
                    existing = existing_by_hash.get(media.digest)
                else:
                    existing = client.media_by_hash(media.digest)
                check_stop()
                if existing is None:
                    client.upload_media(tease_id, media)
                    uploaded += 1
                else:
                    client.add_existing_media(tease_id, media)
                    reused += 1
                checkpoint.add(_deploy_media_key(media))
                dirty_since_flush += 1
                if dirty_since_flush >= CHECKPOINT_FLUSH_EVERY:
                    flush_checkpoint()
                completed += 1
                report({
                    "phase": "media",
                    "completed": completed,
                    "total": total,
                    "uploaded": uploaded,
                    "reused": reused,
                    "skipped": skipped,
                    "remoteChanged": remote_changed,
                    "resuming": resume_media_only,
                    "current": media.name,
                })
        finally:
            # Preserve resume safety on user stop, transport errors, and normal
            # completion without paying for one full checkpoint rewrite per file.
            flush_checkpoint()

        check_stop()
        result = {
            "ok": True,
            "projectId": project_id,
            "teaseId": tease_id,
            "mediaCount": total,
            "uploaded": uploaded,
            "reused": reused,
            "skipped": skipped,
            "totalBytes": plan.total_bytes,
            "resumed": resume_media_only,
            "editorUrl": f"{MILOVANA_ORIGIN}/eos/editor/{tease_id}/edit",
            "backupUrl": f"{MILOVANA_ORIGIN}/eos/editor/{tease_id}/backup",
        }
        report({"phase": "done", **result})
        return result
    except MilovanaBrowserError as exc:
        raise MilovanaDeployError(str(exc)) from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
