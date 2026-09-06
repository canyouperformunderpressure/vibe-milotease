"""Search and acquire supported image galleries with gallery-dl."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
from html.parser import HTMLParser
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SUPPORTED_HOSTS = {
    "pornpics.com": "pornpics",
    "www.pornpics.com": "pornpics",
    "imagefap.com": "imagefap",
    "www.imagefap.com": "imagefap",
    "erome.com": "erome",
    "www.erome.com": "erome",
    "pexels.com": "pexels",
    "www.pexels.com": "pexels",
    "unsplash.com": "unsplash",
    "www.unsplash.com": "unsplash",
    "cc0.cn": "cc0",
    "www.cc0.cn": "cc0",
    "stickpng.com": "stickpng",
    "www.stickpng.com": "stickpng",
}
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
PROJECT_ID_RE = SOURCE_ID_RE
SECRET_QUERY_PARTS = ("auth", "credential", "key", "password", "secret", "session", "sid", "signature", "token")
MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
DIRECT_MEDIA_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
}
MAX_DIRECT_BYTES = 100 * 1024 * 1024
MAX_SOURCE_PAGE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
PAGE_MEDIA_HOSTS = {
    "cc0": {"img.cc0.cn"},
    "stickpng": {"assets.stickpng.com"},
}
_DISCOVERY_LOCK = threading.Lock()


class MediaSourceError(RuntimeError):
    """A user-actionable media search or acquisition error."""


def _gallery_dl_modules() -> tuple[Any, Any, Any, str]:
    try:
        from gallery_dl import __version__, config, extractor
        from gallery_dl.extractor.common import Message
    except ImportError as exc:
        raise MediaSourceError(
            "gallery-dl is missing; install the dependencies from milo-editor/requirements.txt first"
        ) from exc
    return config, extractor, Message, str(__version__)


def _safe_id(value: str, label: str) -> str:
    if not SOURCE_ID_RE.fullmatch(value or ""):
        raise MediaSourceError(f"{label} may contain only letters, digits, dots, underscores, and hyphens, with a maximum length of 80 characters")
    return value


def _safe_url(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or len(value) > 4096:
        raise MediaSourceError("The source URL is invalid or too long")
    parsed = urlsplit(value.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise MediaSourceError("The source URL has an invalid port") from exc
    if parsed.scheme != "https" or parsed.username or parsed.password or port is not None:
        raise MediaSourceError("The source must be an HTTPS URL from a supported site")
    provider = SUPPORTED_HOSTS.get((parsed.hostname or "").casefold())
    if provider is None:
        raise MediaSourceError("Only PornPics, ImageFap, EroMe, Pexels, Unsplash, CC0, and StickPNG URLs are supported")
    return value.strip(), provider


def _public_url(value: str) -> str:
    """Return a provenance URL without fragments or likely credentials."""
    parsed = urlsplit(value)
    pairs = []
    for part in parsed.query.split("&"):
        key = part.partition("=")[0].casefold()
        if part and not any(secret in key for secret in SECRET_QUERY_PARTS):
            pairs.append(part)
    query = "&".join(pairs)
    return parsed._replace(query=query, fragment="").geturl()


def _safe_direct_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise MediaSourceError("The media URL is invalid or too long")
    parsed = urlsplit(value.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise MediaSourceError("The media URL has an invalid port") from exc
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or port is not None:
        raise MediaSourceError("The media URL must be an HTTP/HTTPS URL without embedded credentials or a custom port")
    hostname = parsed.hostname
    if not hostname:
        raise MediaSourceError("The media URL is missing a hostname")
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise MediaSourceError(f"Could not resolve the media URL host: {hostname}") from exc
    for address in addresses:
        candidate = ipaddress.ip_address(address[4][0])
        if isinstance(candidate, ipaddress.IPv6Address) and candidate.ipv4_mapped:
            candidate = candidate.ipv4_mapped
        if not candidate.is_global:
            raise MediaSourceError("The media URL cannot target localhost, private networks, or reserved network addresses")
    return value.strip()


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        self.redirects += 1
        if self.redirects > MAX_REDIRECTS:
            raise MediaSourceError("The media URL redirected too many times")
        safe = _safe_direct_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, safe)


def _download_response(url: str):
    safe = _safe_direct_url(url)
    request = Request(safe, headers={"User-Agent": "MiloAIEditor/0.1 media-import"})
    try:
        return build_opener(_SafeRedirectHandler()).open(request, timeout=20)
    except MediaSourceError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise MediaSourceError(f"Media download failed: {exc}") from exc


class _PageMediaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value for key, value in attrs if value}
        if tag.casefold() == "meta":
            marker = (values.get("property") or values.get("name") or "").casefold()
            if marker in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
                if content := values.get("content"):
                    self.urls.append(content)
        elif tag.casefold() == "link":
            rel = (values.get("rel") or "").casefold().split()
            if "image_src" in rel and (href := values.get("href")):
                self.urls.append(href)
        elif tag.casefold() == "img":
            for key in ("src", "data-src", "data-original", "data-lazy-src"):
                if value := values.get(key):
                    self.urls.append(value)
        elif tag.casefold() == "a" and (href := values.get("href")):
            self.urls.append(href)


def _normalize_page_media_url(value: str, provider: str) -> str:
    parsed = urlsplit(value)
    if provider == "cc0" and "!" in parsed.path:
        base = parsed.path.rsplit("!", 1)[0]
        if Path(base).suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp"}:
            parsed = parsed._replace(path=base)
    return parsed.geturl()


def _page_media_candidates(page_url: str, provider: str, html: str) -> list[str]:
    parser = _PageMediaParser()
    try:
        parser.feed(html)
    except Exception as exc:
        raise MediaSourceError(f"{provider}  page HTML parsing failed: {exc}") from exc

    allowed_hosts = PAGE_MEDIA_HOSTS[provider]
    candidates: list[str] = []
    seen: set[str] = set()
    for raw in parser.urls:
        candidate = _normalize_page_media_url(urljoin(page_url, raw.strip()), provider)
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"}:
            continue
        if (parsed.hostname or "").casefold() not in allowed_hosts:
            continue
        if Path(parsed.path).suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
            continue
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def resolve_page_media_url(url: str) -> tuple[str, str]:
    """Resolve a supported CC0/StickPNG detail page to its public image URL."""
    page_url, provider = _safe_url(url)
    if provider not in PAGE_MEDIA_HOSTS:
        raise MediaSourceError("This site uses gallery-dl and does not require webpage image parsing")

    response = _download_response(page_url)
    final_page_url = response.geturl()
    content_type = response.headers.get_content_type().casefold()
    if content_type not in {"text/html", "application/xhtml+xml"}:
        response.close()
        raise MediaSourceError(f"{provider} URL did not return an HTML page")
    with response:
        body = response.read(MAX_SOURCE_PAGE_BYTES + 1)
    if len(body) > MAX_SOURCE_PAGE_BYTES:
        raise MediaSourceError(f"{provider} page exceeds the 5 MB limit")
    charset = response.headers.get_content_charset() or "utf-8"
    html = body.decode(charset, errors="replace")
    candidates = _page_media_candidates(final_page_url, provider, html)
    if not candidates:
        raise MediaSourceError(f"No downloadable public images were found on the {provider} page")
    return candidates[0], provider


def _direct_filename(url: str, content_type: str, digest: str) -> str:
    suffix = DIRECT_MEDIA_TYPES[content_type]
    raw_name = Path(unquote(urlsplit(url).path)).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(raw_name).stem).strip(".-")[:60]
    return f"{stem + '-' if stem else ''}{digest[:16]}{suffix}"


def fetch_direct_media(
    projects_root: Path,
    project_id: str,
    source_id: str,
    url: str,
    *,
    provider: str = "direct-url",
    provenance_url: str | None = None,
) -> dict[str, Any]:
    """Download one public image or audio URL into the selected project."""
    source_id = _safe_id(source_id, "source-id")
    project_dir = _project_dir(projects_root, project_id)
    destination = (project_dir / "media" / "sources" / source_id).resolve()
    sources_root = (project_dir / "media" / "sources").resolve()
    if destination.parent != sources_root:
        raise MediaSourceError("The source directory escapes the project's media/sources directory")
    destination.mkdir(parents=True, exist_ok=True)

    response = _download_response(url)
    final_url = response.geturl()
    source_url = _public_url(provenance_url or final_url)
    existing_manifest = destination / "source.json"
    if existing_manifest.is_file():
        try:
            previous_url = json.loads(existing_manifest.read_text(encoding="utf-8")).get("source_url")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            response.close()
            raise MediaSourceError(f"The existing source manifest is invalid: {existing_manifest}") from exc
        if previous_url and previous_url != source_url:
            response.close()
            raise MediaSourceError(f"source-id {source_id} already belongs to another URL; use a new source-id")
    content_type = response.headers.get_content_type().casefold()
    if content_type not in DIRECT_MEDIA_TYPES:
        response.close()
        raise MediaSourceError("The URL returned content that is not a supported image or audio file")
    declared = response.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > MAX_DIRECT_BYTES:
                response.close()
                raise MediaSourceError("The media file exceeds the 100 MB limit")
        except ValueError:
            pass

    fd, temporary = tempfile.mkstemp(prefix=".remote.", suffix=".downloading", dir=destination)
    digest = hashlib.sha256()
    size = 0
    try:
        with response, os.fdopen(fd, "wb") as handle:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DIRECT_BYTES:
                    raise MediaSourceError("The media file exceeds the 100 MB limit")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if size == 0:
            raise MediaSourceError("The media URL returned an empty file")
        filename = _direct_filename(final_url, content_type, digest.hexdigest())
        final_path = destination / filename
        if final_path.exists():
            Path(temporary).unlink(missing_ok=True)
        else:
            Path(temporary).replace(final_path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise

    relative = destination.relative_to(project_dir).as_posix()
    record = {
        "path": filename,
        "name": Path(unquote(urlsplit(final_url).path)).name or filename,
        "size": size,
        "sha256": digest.hexdigest(),
        "mime_type": content_type,
    }
    manifest = {
        "format": "milo-media-source",
        "provider": provider,
        "source_url": source_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "files": [record],
    }
    _atomic_json(destination / "source.json", manifest)
    return {
        "project_id": project_id,
        "source_id": source_id,
        "provider": provider,
        "source_url": manifest["source_url"],
        "source_folder": relative,
        "file_count": 1,
        "manifest": f"{relative}/source.json",
        "files": [{"path": f"{relative}/{filename}", "name": record["name"], "mimeType": content_type, "size": size}],
        "asset_yaml": {source_id: {"file": f"{relative}/{filename}", "type": "audio" if content_type.startswith("audio/") else "image"}},
    }


def fetch_page_media(projects_root: Path, project_id: str, source_id: str, url: str) -> dict[str, Any]:
    """Resolve a supported public image detail page and download its image."""
    media_url, provider = resolve_page_media_url(url)
    return fetch_direct_media(
        projects_root,
        project_id,
        source_id,
        media_url,
        provider=provider,
        provenance_url=url,
    )


def fetch_media_url(
    projects_root: Path,
    project_id: str,
    source_id: str,
    url: str,
    cookies_file: str | None = None,
) -> dict[str, Any]:
    """Dispatch gallery pages, supported detail pages, and direct media URLs."""
    parsed = urlsplit(url.strip() if isinstance(url, str) else "")
    suffix = Path(parsed.path).suffix.casefold()
    provider = SUPPORTED_HOSTS.get((parsed.hostname or "").casefold())
    if provider in PAGE_MEDIA_HOSTS and suffix not in MEDIA_SUFFIXES:
        return fetch_page_media(projects_root, project_id, source_id, url)
    if provider and suffix not in MEDIA_SUFFIXES:
        return fetch_gallery(projects_root, project_id, source_id, url, cookies_file)
    return fetch_direct_media(projects_root, project_id, source_id, url)


def discovery_url(provider: str, query: str) -> str:
    provider = provider.casefold()
    if not query or not query.strip():
        raise MediaSourceError("The search query cannot be empty")
    encoded = quote_plus(query.strip())
    if provider == "pornpics":
        return f"https://www.pornpics.com/?q={encoded}"
    if provider == "erome":
        return f"https://www.erome.com/search?q={encoded}"
    if provider == "imagefap":
        raise MediaSourceError("ImageFap has no gallery-dl search extractor; provide a folder, gallery, image, or profile URL found on the site")
    if provider in {"cc0", "stickpng", "pexels", "unsplash"}:
        raise MediaSourceError(f"--provider {provider} supports --url only and does not support --query search")
    raise MediaSourceError("provider must be pornpics, imagefap, or erome")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if isinstance(key, str) and not key.startswith("_"):
                result[key] = _json_value(item)
        return result
    return str(value)


def discover_candidates(url: str, limit: int = 20) -> dict[str, Any]:
    """Read parent extractor Queue records without resolving child galleries."""
    url, provider = _safe_url(url)
    if limit < 1 or limit > 100:
        raise MediaSourceError("limit must be between 1 and 100")
    config, extractor, message, version = _gallery_dl_modules()
    candidates: list[dict[str, Any]] = []
    with _DISCOVERY_LOCK:
        config.clear()
        config.set(("extractor",), "input", False)
        config.set(("extractor",), "netrc", False)
        config.set(("extractor",), "proxy-env", False)
        config.set(("extractor",), "retries", 2)
        config.set(("extractor",), "timeout", 30)
        config.set(("cache",), "file", ":memory:")
        selected = extractor.find(url)
        if selected is None:
            raise MediaSourceError("gallery-dl does not support this URL")
        try:
            for item in selected:
                if not item or item[0] is not message.Queue:
                    continue
                candidate_url = item[1]
                if not isinstance(candidate_url, str):
                    continue
                metadata = _json_value(item[2] if len(item) > 2 and isinstance(item[2], dict) else {})
                candidates.append({"url": _public_url(candidate_url), "metadata": metadata})
                if len(candidates) >= limit:
                    break
        except Exception as exc:
            raise MediaSourceError(f"gallery-dl candidate discovery failed: {exc}") from exc
    if not candidates:
        raise MediaSourceError("This URL produced no candidate galleries; if it is already a gallery, use media-fetch directly")
    return {
        "provider": provider,
        "source_url": _public_url(url),
        "gallery_dl_version": version,
        "candidates": candidates,
    }


def _project_dir(projects_root: Path, project_id: str) -> Path:
    project_id = _safe_id(project_id, "project-id")
    root = projects_root.resolve()
    project_dir = (root / project_id).resolve()
    if project_dir.parent != root or not (project_dir / "project.json").is_file():
        raise MediaSourceError(f"Project not found: {project_id}")
    return project_dir


def _atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _file_records(root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix().casefold()):
        if path.suffix.casefold() not in MEDIA_SUFFIXES:
            continue
        content = path.read_bytes()
        records.append({
            "path": path.relative_to(root).as_posix(),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    return records


def fetch_gallery(
    projects_root: Path,
    project_id: str,
    source_id: str,
    url: str,
    cookies_file: str | None = None,
) -> dict[str, Any]:
    """Download one selected gallery into the project's media/sources tree."""
    source_id = _safe_id(source_id, "source-id")
    url, provider = _safe_url(url)
    project_dir = _project_dir(projects_root, project_id)
    destination = (project_dir / "media" / "sources" / source_id).resolve()
    sources_root = (project_dir / "media" / "sources").resolve()
    if destination.parent != sources_root:
        raise MediaSourceError("The source directory escapes the project's media/sources directory")
    sources_root.mkdir(parents=True, exist_ok=True)
    existing_manifest = destination / "source.json"
    if existing_manifest.is_file():
        try:
            previous_url = json.loads(existing_manifest.read_text(encoding="utf-8")).get("source_url")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            raise MediaSourceError(f"The existing source manifest is invalid: {existing_manifest}") from exc
        if previous_url and previous_url != _public_url(url):
            raise MediaSourceError(f"source-id {source_id} already belongs to another URL; use a new source-id")
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / ".download-archive.sqlite3"
    command = [
        sys.executable,
        "-m",
        "gallery_dl",
        "--config-ignore",
        "--no-input",
        "--windows-filenames",
        "--no-postprocessors",
        "--directory",
        str(destination),
        "--download-archive",
        str(archive),
        "--write-info-json",
    ]
    if cookies_file:
        cookies = Path(cookies_file).expanduser().resolve()
        if not cookies.is_file():
            raise MediaSourceError(f"Cookies file not found: {cookies}")
        command.extend(("--cookies", str(cookies)))
    command.append(url)

    try:
        completed = subprocess.run(
            command,
            cwd=project_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise MediaSourceError("gallery-dl is missing; install the dependencies from milo-editor/requirements.txt first") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaSourceError("gallery-dl exceeded the 30-minute timeout; downloaded files remain in the source directory") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise MediaSourceError(f"gallery-dl download failed ({completed.returncode})：{detail[-1200:] or 'no error details'}")

    try:
        _, _, _, version = _gallery_dl_modules()
    except MediaSourceError:
        version = "unknown"
    files = _file_records(destination)
    if not files:
        raise MediaSourceError("gallery-dl did not download any media files")
    manifest = {
        "format": "milo-media-source",
        "provider": provider,
        "source_url": _public_url(url),
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "gallery_dl_version": version,
        "files": files,
    }
    _atomic_json(destination / "source.json", manifest)
    relative = destination.relative_to(project_dir).as_posix()
    return {
        "project_id": project_id,
        "source_id": source_id,
        "provider": provider,
        "source_url": manifest["source_url"],
        "source_folder": relative,
        "file_count": len(files),
        "manifest": f"{relative}/source.json",
        "files": [
            {
                "path": f"{relative}/{item['path']}",
                "name": Path(item["path"]).name,
                "mimeType": mimetypes.guess_type(item["path"])[0] or "application/octet-stream",
                "size": item["size"],
            }
            for item in files
        ],
        "asset_yaml": {source_id: {"folder": relative, "include": ["*.jpg", "*.jpeg", "*.png", "*.webp"]}},
    }
