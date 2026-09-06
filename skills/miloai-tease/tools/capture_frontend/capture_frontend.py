from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILL_ROOT.parents[1]
APP_ROOT = REPO_ROOT / "milo-editor"
EDITOR_ROOT = APP_ROOT / "editor-web"
ASSET_ROOT = EDITOR_ROOT / "assets"
CAPTURE_ROOT = APP_ROOT / "captures" / "frontend-source"
BASE_URL = "https://milovana.com"
INDEX_URL = f"{BASE_URL}/eos/editor/teases"
ENTRY_ASSETS = {"index-3db13f53.js", "index-b972f030.css"}
ASSET_RE = re.compile(rb"(?:assets/|\./)?([A-Za-z0-9_.-]+-[0-9a-f]{8}\.(?:js|css|woff2?|png|jpe?g|svg))")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MiloAIEditor-asset-capture/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
    index_data = fetch(INDEX_URL)
    (CAPTURE_ROOT / "index.html").write_bytes(index_data)
    local_index = index_data.replace(b"https://milovana.com/eos/editor/assets/", b"/eos/editor/assets/")
    EDITOR_ROOT.joinpath("index.html").write_bytes(local_index)

    pending = set(ENTRY_ASSETS)
    pending.update(match.decode("ascii") for match in ASSET_RE.findall(index_data))
    captured: dict[str, dict[str, object]] = {}
    while pending:
        name = pending.pop()
        if name in captured:
            continue
        url = f"{BASE_URL}/eos/editor/assets/{name}"
        data = fetch(url)
        target = ASSET_ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        captured[name] = {"source": url, "sha256": sha256(data), "size": len(data)}
        pending.update(match.decode("ascii") for match in ASSET_RE.findall(data) if match.decode("ascii") not in captured)
        if name.endswith(".js"):
            map_name = f"{name}.map"
            try:
                map_data = fetch(f"{url}.map")
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
            else:
                (ASSET_ROOT / map_name).write_bytes(map_data)
                captured[map_name] = {"source": f"{url}.map", "sha256": sha256(map_data), "size": len(map_data)}

    manifest = {
        "source": INDEX_URL,
        "capturedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "indexSha256": sha256(index_data),
        "assets": dict(sorted(captured.items())),
    }
    (CAPTURE_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(captured)} assets")


if __name__ == "__main__":
    main()
