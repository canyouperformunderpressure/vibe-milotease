from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILL_ROOT.parents[1]
EDITOR_ROOT = REPO_ROOT / "milo-editor"
sys.path.insert(0, str(EDITOR_ROOT))

from app.storage import ProjectStore


def copy_tree_preserving_source(source: Path, destination: Path) -> int:
    copied = 0
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        target = destination / source_file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size == source_file.stat().st_size:
            continue
        if target.exists():
            target = target.with_name(f"{target.name}.imported-copy")
        shutil.copy2(source_file, target)
        copied += 1
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an EOS project without modifying its source directory.")
    parser.add_argument("source", type=Path)
    parser.add_argument("project_id")
    parser.add_argument("--title")
    parser.add_argument("--author", default="Local Author")
    args = parser.parse_args()

    source = args.source.resolve()
    script_path = source / "eosscript.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    store = ProjectStore()
    project_dir = store.project_dir(args.project_id)
    if not (project_dir / "project.json").exists():
        store.create_project(args.project_id, args.title or source.name, args.author, script)

    media_source = source / "timg"
    copied = copy_tree_preserving_source(media_source, project_dir / "media" / "timg") if media_source.is_dir() else 0
    print(json.dumps({"projectId": args.project_id, "mediaFilesCopied": copied, "projectDir": str(project_dir)}))


if __name__ == "__main__":
    main()
