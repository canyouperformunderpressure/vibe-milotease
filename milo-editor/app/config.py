from __future__ import annotations

import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
PROJECTS_ROOT = Path(os.environ.get("MILO_PROJECTS_ROOT", REPO_ROOT / "projects")).resolve()
EDITOR_ROOT = Path(os.environ.get("MILO_EDITOR_ROOT", APP_ROOT / "editor-web")).resolve()
RUNTIME_ROOT = Path(
    os.environ.get("MILO_RUNTIME_ROOT", APP_ROOT / "runtime")
).resolve()
CAPTURES_ROOT = Path(os.environ.get("MILO_CAPTURES_ROOT", APP_ROOT / "captures")).resolve()
MONACO_ROOT = Path(
    os.environ.get("MILO_MONACO_ROOT", APP_ROOT / "vendor" / "monaco" / "vs")
).resolve()
TEASE_GRAPH_ROOT = Path(
    os.environ.get("MILO_TEASE_GRAPH_ROOT", APP_ROOT / "tease-graph" / "dist")
).resolve()

HOST = "127.0.0.1"
PORT = int(os.environ.get("MILO_PORT", "8000"))
