from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from .config import REPO_ROOT

MILOVANA_ORIGIN = "https://milovana.com"
MILOVANA_CREATE_URL = f"{MILOVANA_ORIGIN}/eos/editor/create"
CDP_HOST = "127.0.0.1"
CDP_PORT = int(os.environ.get("MILOVANA_CDP_PORT", "9223"))
CDP_URL = f"http://{CDP_HOST}:{CDP_PORT}"
BROWSER_PROFILE_ROOT = Path(
    os.environ.get("MILOVANA_BROWSER_PROFILE", REPO_ROOT / "temp" / "milovana-browser")
).resolve()

TEASES_QUERY = """
query Teases {
  me {
    id
    allTeases { __typename id title }
  }
}
"""

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

LOAD_TEASE_SCRIPT = """
query LoadTeaseScript($teaseId: ID!) {
  tease(id: $teaseId) {
    __typename
    ... on EosTease {
      id
      script
    }
  }
}
"""


class MilovanaBrowserError(RuntimeError):
    pass


def find_chrome_executable() -> Path | None:
    configured = os.environ.get("MILOVANA_CHROME")
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    return None


def _cdp_version(timeout: float = 0.5) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def browser_runtime_status() -> dict[str, Any]:
    chrome = find_chrome_executable()
    version = _cdp_version()
    return {
        "available": chrome is not None,
        "running": version is not None,
        "browser": version.get("Browser") if version else None,
        "profile": BROWSER_PROFILE_ROOT.name,
    }


def launch_browser(*, url: str = MILOVANA_CREATE_URL, timeout: float = 12.0) -> dict[str, Any]:
    chrome = find_chrome_executable()
    if chrome is None:
        raise MilovanaBrowserError("Google Chrome or Microsoft Edge could not be found.")
    if _cdp_version() is None:
        BROWSER_PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
        args = [
            str(chrome),
            f"--remote-debugging-port={CDP_PORT}",
            f"--remote-debugging-address={CDP_HOST}",
            f"--user-data-dir={BROWSER_PROFILE_ROOT}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            url,
        ]
        subprocess.Popen(
            args,
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _cdp_version() is not None:
                break
            time.sleep(0.15)
        else:
            raise MilovanaBrowserError("Chrome started, but the local CDP connection did not become ready.")
    return browser_runtime_status()


class MilovanaBrowserClient:
    """Run Milovana API calls inside a real, user-visible browser session."""

    def __init__(self, timeout: float = 90.0):
        launch_browser()
        self.timeout = timeout
        self._upload_page: Page | None = None
        self._playwright: Playwright = sync_playwright().start()
        try:
            self._browser: Browser = self._playwright.chromium.connect_over_cdp(
                CDP_URL, timeout=int(timeout * 1000)
            )
            contexts = self._browser.contexts
            if not contexts:
                raise MilovanaBrowserError("Chrome has no usable browser context.")
            self._context = contexts[0]
            self.page = self._choose_page()
        except Exception:
            self._playwright.stop()
            raise

    def _choose_page(self) -> Page:
        milovana_pages = [page for page in self._context.pages if page.url.startswith(MILOVANA_ORIGIN)]
        for page in milovana_pages:
            if "/eos/editor" in page.url:
                try:
                    if "just a moment" not in page.title().casefold():
                        return page
                except Exception:
                    return page
        if milovana_pages:
            return milovana_pages[-1]
        page = self._context.new_page()
        page.goto(MILOVANA_CREATE_URL, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
        return page

    def close(self) -> None:
        upload_page = getattr(self, "_upload_page", None)
        if upload_page is not None:
            try:
                if not upload_page.is_closed():
                    upload_page.close()
            except Exception:
                pass
            self._upload_page = None
        self._playwright.stop()

    def __enter__(self) -> "MilovanaBrowserClient":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def _ensure_milovana_origin(self) -> None:
        if not self.page.url.startswith(MILOVANA_ORIGIN):
            self.page.goto(
                MILOVANA_CREATE_URL,
                wait_until="domcontentloaded",
                timeout=int(self.timeout * 1000),
            )

    def focus_tease(self, tease_id: str) -> None:
        clean_id = str(tease_id or "").strip()
        if not clean_id.isdigit():
            raise MilovanaBrowserError("Milovana tease ID must be numeric.")
        target = f"{MILOVANA_ORIGIN}/eos/editor/{clean_id}/edit"
        if not self.page.url.startswith(target):
            self.page.goto(
                target,
                wait_until="domcontentloaded",
                timeout=int(self.timeout * 1000),
            )
        try:
            self.page.bring_to_front()
        except Exception:
            pass

    @staticmethod
    def _looks_like_cloudflare_challenge(text: str) -> bool:
        lowered = text.casefold()
        markers = (
            "just a moment",
            "cf-chl-",
            "challenge-platform",
            "cloudflare ray id",
            "ray id:",
            "verify you are human",
            "正在进行安全验证",
            "安全服务防护恶意自动程序",
            "验证您不是自动程序",
            "由 cloudflare 提供的性能和安全服务",
        )
        return any(marker in lowered for marker in markers)

    def graphql(
        self,
        query: str,
        variables: dict[str, Any],
        operation_name: str | None = None,
        *,
        patient: bool = True,
    ) -> dict[str, Any]:
        self._ensure_milovana_origin()
        result: dict[str, Any] = {}
        # Long deploys issue hundreds of same-origin requests. Cloudflare may
        # occasionally answer one XHR with a short-lived 403/challenge page even
        # though the visible Eos Editor session is healthy. Treat that as a
        # recoverable transport event before asking the user to intervene.
        retry_delays = (2.0, 5.0, 10.0, 20.0) if patient else (0.35, 1.0)
        for attempt in range(len(retry_delays) + 1):
            result = self.page.evaluate(
                """async ({query, variables, operationName}) => {
                    const endpoint = document.cookie.includes('EOS_FEAT_2020_WINTA=1') ? '/winta/' : '/graphql/';
                    const response = await fetch(endpoint, {
                        method: 'POST',
                        credentials: 'include',
                        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                        body: JSON.stringify({query, variables, operationName})
                    });
                    return {
                        status: response.status,
                        text: await response.text(),
                        url: location.href,
                        contentType: response.headers.get('content-type') || ''
                    };
                }""",
                {"query": query, "variables": variables, "operationName": operation_name},
            )
            status = int(result.get("status") or 0)
            if status != 403 or attempt == len(retry_delays):
                break
            time.sleep(retry_delays[attempt])

        status = int(result.get("status") or 0)
        text = str(result.get("text") or "")
        if status >= 400:
            if status == 403 and self._looks_like_cloudflare_challenge(text):
                raise MilovanaBrowserError(
                    "Milovana background GraphQL requests repeatedly returned a Cloudflare challenge; "
                    "the top-level EOS Editor page may look normal and show no challenge. Retry Deploy later."
                )
            if status == 403:
                raise MilovanaBrowserError(
                    "Milovana GraphQL temporarily returned HTTP 403, but the current page may not show a Cloudflare challenge. Retry Deploy; if it persists, refresh the EOS Editor page in the dedicated Chrome window."
                )
            raise MilovanaBrowserError(f"Milovana HTTP {status}: {text[:300]}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            if self._looks_like_cloudflare_challenge(text):
                raise MilovanaBrowserError(
                    "Milovana is returning a Cloudflare verification page; complete the challenge in the browser and retry."
                ) from exc
            raise MilovanaBrowserError("Milovana GraphQL returned an unparseable response.") from exc
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            message = "; ".join(str(item.get("message") or item) for item in errors[:3])
            raise MilovanaBrowserError(f"Milovana GraphQL error: {message}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else {}

    def session_status(self) -> dict[str, Any]:
        try:
            data = self.graphql(TEASES_QUERY, {}, "Teases", patient=False)
        except MilovanaBrowserError as exc:
            return {
                "running": True,
                "authenticated": False,
                "ready": False,
                "message": str(exc),
                "url": self.page.url,
            }
        me = data.get("me")
        authenticated = isinstance(me, dict) and str(me.get("id") or "").isdigit() and int(me["id"]) > 1
        return {
            "running": True,
            "authenticated": authenticated,
            "ready": authenticated,
            "message": "The Milovana browser is signed in and ready to deploy." if authenticated else "Sign in to Milovana in the opened Chrome window.",
            "url": self.page.url,
        }

    def list_eos_teases(self) -> list[dict[str, str]]:
        data = self.graphql(TEASES_QUERY, {}, "Teases", patient=False)
        me = data.get("me") if isinstance(data, dict) else None
        authenticated = isinstance(me, dict) and str(me.get("id") or "").isdigit() and int(me["id"]) > 1
        if not authenticated:
            raise MilovanaBrowserError("Sign in to Milovana in the opened Chrome window.")
        teases = me.get("allTeases")
        result: list[dict[str, str]] = []
        for tease in teases or []:
            if not isinstance(tease, dict) or tease.get("__typename") != "EosTease":
                continue
            tease_id = str(tease.get("id") or "")
            if not tease_id.isdigit():
                continue
            result.append({"id": tease_id, "title": str(tease.get("title") or f"Tease #{tease_id}")})
        result.sort(key=lambda item: int(item["id"]), reverse=True)
        return result

    def require_authenticated(self) -> None:
        status = self.session_status()
        if not status.get("authenticated"):
            raise MilovanaBrowserError(str(status.get("message") or "The Milovana browser is not signed in yet."))

    def create_tease(self, title: str) -> str:
        data = self.graphql(CREATE_TEASE, {"title": title}, "CreateTease")
        result = data.get("createTease")
        tease_id = str(result.get("id") or "") if isinstance(result, dict) else ""
        if not tease_id.isdigit():
            raise MilovanaBrowserError("Milovana did not return a new tease ID.")
        return tease_id

    def media_by_hash(self, digest: str) -> dict[str, Any] | None:
        data = self.graphql(CHECK_MEDIA_HASH, {"hash": digest}, "checkMediaHash")
        media = data.get("mediaByHash")
        return media if isinstance(media, dict) else None

    def media_by_hashes(self, digests: list[str]) -> dict[str, dict[str, Any] | None]:
        """Resolve media hashes efficiently, degrading safely around Cloudflare.

        The fast path uses GraphQL aliases to resolve a batch in one request. If
        Cloudflare rejects that request, progressively split the batch. Small
        blocked batches fall back to the original single-hash query, which uses
        the longer 2s/5s/10s/20s retry schedule instead of aborting Deploy.
        """
        unique = list(dict.fromkeys(str(digest) for digest in digests if digest))
        if not unique:
            return {}
        if len(unique) == 1:
            digest = unique[0]
            return {digest: self.media_by_hash(digest)}

        fields = []
        variables: dict[str, Any] = {}
        declarations = []
        for index, digest in enumerate(unique):
            key = f"h{index}"
            variable = f"hash{index}"
            declarations.append(f"${variable}: String!")
            fields.append(
                f"{key}: mediaByHash(hash: ${variable}) {{ id mimeType size dimensions {{ width height }} }}"
            )
            variables[variable] = digest
        query = "query checkMediaHashes(" + ", ".join(declarations) + ") {\n" + "\n".join(fields) + "\n}"

        try:
            data = self.graphql(query, variables, "checkMediaHashes", patient=False)
        except MilovanaBrowserError as exc:
            message = str(exc).lower()
            retryable_block = "cloudflare" in message or "http 403" in message
            if not retryable_block:
                raise

            # Give transient Cloudflare state a moment to clear before changing
            # request shape. Large alias queries are then split recursively.
            time.sleep(2.0)
            if len(unique) > 4:
                midpoint = len(unique) // 2
                left = self.media_by_hashes(unique[:midpoint])
                time.sleep(0.25)
                right = self.media_by_hashes(unique[midpoint:])
                return {**left, **right}

            # If even a tiny alias query is challenged, use the proven single
            # query path with its patient retry schedule. This is slower only
            # while Cloudflare is actively rejecting the optimized request.
            return {digest: self.media_by_hash(digest) for digest in unique}

        result: dict[str, dict[str, Any] | None] = {}
        for index, digest in enumerate(unique):
            value = data.get(f"h{index}")
            result[digest] = value if isinstance(value, dict) else None
        return result

    def add_existing_media(self, tease_id: str, media: Any) -> dict[str, Any]:
        data = self.graphql(
            ADD_FILE_TO_TEASE,
            {"teaseId": tease_id, "hash": media.digest, "name": media.name},
            "addFileToTease",
        )
        result = data.get("addFileToTease")
        if not isinstance(result, dict):
            raise MilovanaBrowserError(f"Existing media {media.name} could not be attached to the tease.")
        return result

    def _get_upload_page(self, tease_id: str) -> Page:
        page = getattr(self, "_upload_page", None)
        if page is None or page.is_closed():
            page = self._context.new_page()
            page.goto(
                f"{MILOVANA_ORIGIN}/eos/editor/{tease_id}/edit",
                wait_until="domcontentloaded",
                timeout=int(self.timeout * 1000),
            )
            self._upload_page = page
        elif not page.url.startswith(MILOVANA_ORIGIN):
            page.goto(
                f"{MILOVANA_ORIGIN}/eos/editor/{tease_id}/edit",
                wait_until="domcontentloaded",
                timeout=int(self.timeout * 1000),
            )
        return page

    def _prepare_top_level_upload_form(self, page: Page, tease_id: str, media: Any) -> None:
        page.evaluate(
            """teaseId => {
                const old = document.querySelector('#milo-top-upload-form');
                if (old) old.remove();
                const form = document.createElement('form');
                form.id = 'milo-top-upload-form';
                form.method = 'POST';
                form.enctype = 'multipart/form-data';
                form.action = '/api/eos/upload.php?id=' + encodeURIComponent(teaseId);
                const filename = document.createElement('input');
                filename.type = 'hidden';
                filename.name = 'Filename';
                filename.id = 'milo-top-filename';
                const file = document.createElement('input');
                file.type = 'file';
                file.name = 'Filedata';
                file.id = 'milo-top-file';
                file.style.display = 'none';
                form.appendChild(filename);
                form.appendChild(file);
                document.body.appendChild(form);
            }""",
            tease_id,
        )
        page.locator("#milo-top-file").set_input_files(str(media.path))
        # Local materialized files are named by hash. Rename the browser File
        # object to the logical EOS name before the native form POST so audio
        # and file entries keep a useful remote name as far as Milovana allows.
        page.locator("#milo-top-file").evaluate(
            """(input, filename) => {
                const source = input.files && input.files[0];
                if (!source) throw new Error('Local file was not attached to browser input');
                const renamed = new File([source], filename, {
                    type: source.type,
                    lastModified: source.lastModified
                });
                const transfer = new DataTransfer();
                transfer.items.add(renamed);
                input.files = transfer.files;
            }""",
            media.name,
        )
        page.locator("#milo-top-filename").evaluate("(el, value) => el.value = value", media.name)

    def _upload_media_fetch(self, tease_id: str, media: Any) -> tuple[int, str]:
        """Upload with the same same-origin fetch/FormData path as Milovana's UI."""
        self._ensure_milovana_origin()
        result = self.page.evaluate(
            """async ({teaseId, path, name}) => {
                const input = document.createElement('input');
                input.type = 'file';
                input.style.display = 'none';
                input.id = 'milo-fast-upload-file';
                document.body.appendChild(input);
                return {ready: true};
            }""",
            {"teaseId": tease_id, "path": str(media.path), "name": media.name},
        )
        if not isinstance(result, dict) or not result.get("ready"):
            raise MilovanaBrowserError(f"Could not prepare browser upload for {media.name}.")
        locator = self.page.locator("#milo-fast-upload-file")
        try:
            locator.set_input_files(str(media.path))
            response = locator.evaluate(
                """async (input, args) => {
                    const source = input.files && input.files[0];
                    if (!source) throw new Error('Local file was not attached to browser input');
                    const renamed = new File([source], args.name, {
                        type: source.type,
                        lastModified: source.lastModified
                    });
                    const form = new FormData();
                    form.append('Filename', args.name);
                    form.append('Filedata', renamed, args.name);
                    const res = await fetch('/api/eos/upload.php?id=' + encodeURIComponent(args.teaseId), {
                        method: 'POST',
                        credentials: 'include',
                        body: form
                    });
                    return {status: res.status, text: await res.text()};
                }""",
                {"teaseId": tease_id, "name": media.name},
            )
        finally:
            try:
                self.page.locator("#milo-fast-upload-file").evaluate("el => el.remove()")
            except Exception:
                pass
        if not isinstance(response, dict):
            raise MilovanaBrowserError(f"Uploading {media.name} returned an unexpected browser response.")
        return int(response.get("status") or 0), str(response.get("text") or "")

    def _upload_media_navigation_fallback(self, tease_id: str, media: Any) -> dict[str, Any]:
        """Reliable visible-browser fallback used when fetch is challenged."""
        page = self._get_upload_page(tease_id)
        max_attempts = 5
        challenge_wait_seconds = max(self.timeout, 120.0)

        for attempt in range(1, max_attempts + 1):
            self._prepare_top_level_upload_form(page, tease_id, media)
            with page.expect_navigation(wait_until="domcontentloaded", timeout=int(self.timeout * 1000)):
                page.locator("#milo-top-upload-form").evaluate("form => form.submit()")

            text = page.locator("body").inner_text().strip()
            title = page.title()
            if self._looks_like_cloudflare_challenge(f"{title}\n{text}"):
                # Keep the real browser visible so an interactive challenge can
                # be completed, then replay the exact same local file. A page
                # shown after clearance is not the response to the blocked POST,
                # so it must never be parsed as upload JSON.
                page.bring_to_front()
                deadline = time.monotonic() + challenge_wait_seconds
                while time.monotonic() < deadline:
                    time.sleep(1.0)
                    try:
                        text = page.locator("body").inner_text().strip()
                        title = page.title()
                    except Exception:
                        continue
                    if not self._looks_like_cloudflare_challenge(f"{title}\n{text}"):
                        break
                else:
                    raise MilovanaBrowserError(
                        f"Uploading {media.name} is still waiting on Cloudflare verification after "
                        f"{int(challenge_wait_seconds)} seconds. Complete the verification in the dedicated "
                        "Milovana browser, then use Retry / Resume; completed media will be kept."
                    )

                if attempt < max_attempts:
                    time.sleep(min(2.0, 0.5 * attempt))
                    continue
                raise MilovanaBrowserError(
                    f"Uploading {media.name} kept triggering Cloudflare verification across {max_attempts} "
                    "automatic upload attempts. Use Retry / Resume after the verification page clears."
                )

            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                # Localized Cloudflare pages are checked above. Anything left
                # here is a genuinely unexpected Milovana response.
                raise MilovanaBrowserError(
                    f"Uploading {media.name} returned an unparseable page from Milovana: {text[:300]}"
                ) from exc
            if not isinstance(payload, dict):
                raise MilovanaBrowserError(f"Uploading {media.name} returned an unexpected response format.")
            return payload

        raise MilovanaBrowserError(f"Uploading {media.name} exhausted the automatic retry attempts.")

    def upload_media(self, tease_id: str, media: Any) -> dict[str, Any]:
        # Prefer Milovana's own fast same-origin fetch path. If Cloudflare blocks
        # the background request, retain the existing visible top-level form
        # navigation as a compatibility fallback.
        status, text = self._upload_media_fetch(tease_id, media)
        if status == 403 or self._looks_like_cloudflare_challenge(text):
            payload = self._upload_media_navigation_fallback(tease_id, media)
        else:
            if status >= 400:
                raise MilovanaBrowserError(f"Uploading {media.name} returned HTTP {status}: {text[:300]}")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise MilovanaBrowserError(
                    f"Uploading {media.name} returned invalid JSON from Milovana: {text[:300]}"
                ) from exc

        if not isinstance(payload, dict) or payload.get("error") or payload.get("errors"):
            raise MilovanaBrowserError(f"Uploading {media.name} failed: {payload}")
        remote_hash = str((payload.get("mediaHash") or {}).get("hash") or "")
        if remote_hash and remote_hash != str(media.digest):
            raise MilovanaBrowserError(
                f"Uploading {media.name} returned a hash mismatch: expected {media.digest}, Milovana returned {remote_hash}."
            )
        return payload

    def validate_script(self, tease_id: str, script_text: str) -> list[dict[str, Any]]:
        data = self.graphql(
            VALIDATE_SCRIPT,
            {"teaseId": tease_id, "script": script_text},
            "validateScript",
        )
        validation = data.get("validateEosScript") or {}
        errors = validation.get("validationErrors") or []
        return [item for item in errors if isinstance(item, dict)]

    def load_script(self, tease_id: str) -> str:
        data = self.graphql(
            LOAD_TEASE_SCRIPT,
            {"teaseId": tease_id},
            "LoadTeaseScript",
        )
        tease = data.get("tease")
        if not isinstance(tease, dict) or tease.get("__typename") != "EosTease":
            raise MilovanaBrowserError(f"Milovana tease #{tease_id} is not a readable EOS tease.")
        script = tease.get("script")
        if not isinstance(script, str):
            raise MilovanaBrowserError(f"Milovana tease #{tease_id} did not return an EOS script.")
        return script

    def save_script(self, tease_id: str, script_text: str) -> None:
        data = self.graphql(
            SAVE_SCRIPT,
            {"teaseId": tease_id, "script": script_text},
            "SaveScript",
        )
        if not isinstance(data.get("saveEosScript"), dict):
            raise MilovanaBrowserError("Milovana did not confirm that saveEosScript succeeded.")


def authenticated_browser_status() -> dict[str, Any]:
    runtime = browser_runtime_status()
    if not runtime["running"]:
        return {**runtime, "authenticated": False, "ready": False, "message": "The Milovana browser has not been opened yet."}
    try:
        with MilovanaBrowserClient(timeout=20.0) as client:
            return {**runtime, **client.session_status()}
    except Exception as exc:
        return {**runtime, "authenticated": False, "ready": False, "message": str(exc)}
