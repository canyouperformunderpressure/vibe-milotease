from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceIssue:
    level: str
    code: str
    message: str
    path: str = ""

    def as_dict(self) -> dict[str, str]:
        result = {"level": self.level, "code": self.code, "message": self.message}
        if self.path:
            result["path"] = self.path
        return result


class MiloSourceError(RuntimeError):
    def __init__(self, issues: list[SourceIssue] | tuple[SourceIssue, ...]):
        self.issues = tuple(issues)
        errors = [issue for issue in self.issues if issue.level == "error"]
        visible = errors or list(self.issues)
        message = "; ".join(
            f"{issue.path}: {issue.message}" if issue.path else issue.message
            for issue in visible[:8]
        )
        if len(visible) > 8:
            message += f"; plus {len(visible) - 8} more issues"
        super().__init__(message or "Milo source validation failed")


@dataclass(frozen=True)
class OutlineEdge:
    target: str
    when: str = ""
    priority: str = "main"


@dataclass(frozen=True)
class OutlineNode:
    node_id: str
    name: str
    content: str
    next: tuple[OutlineEdge, ...]


@dataclass(frozen=True)
class OutlineDocument:
    title: str
    brief: str
    entry: str
    nodes: dict[str, OutlineNode]


@dataclass(frozen=True)
class AssetDefinition:
    asset_id: str
    source: str | None = None
    folder: str | None = None
    file: str | None = None
    locator: str | None = None
    pick: str = "sequence"
    recursive: bool = True
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    media_type: str | None = None


@dataclass(frozen=True)
class RuntimeDocument:
    state: dict[str, Any]
    assets: dict[str, AssetDefinition]
    eos: dict[str, Any]
    unknown_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    kind: str
    value: Any
    path: str


@dataclass(frozen=True)
class Page:
    page_id: str
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class SceneDocument:
    scene_id: str
    entry: str
    pages: dict[str, Page]
    source_path: Path | None = None


@dataclass(frozen=True)
class SourceBundle:
    outline: OutlineDocument
    runtime: RuntimeDocument
    scenes: dict[str, SceneDocument]


@dataclass
class MaterializedAsset:
    asset_id: str
    direct_locator: str | None = None
    gallery_id: str | None = None
    images: list[dict[str, Any]] = field(default_factory=list)
    image_names: dict[str, int] = field(default_factory=dict)
    ambiguous_image_names: set[str] = field(default_factory=set)
    audio: list[dict[str, Any]] = field(default_factory=list)
    audio_names: dict[str, str] = field(default_factory=dict)
    ambiguous_audio_names: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class BuildProduct:
    script: dict[str, Any]
    warnings: tuple[SourceIssue, ...] = ()
    materialized_files: tuple[str, ...] = ()
