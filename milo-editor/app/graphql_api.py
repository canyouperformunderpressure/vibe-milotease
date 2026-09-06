from __future__ import annotations

import json
import re
from typing import Any

from .storage import GeneratedArtifactReadOnlyError, NotFoundError, ProjectStore, ValidationError

try:
    from graphql import OperationDefinitionNode, parse
except ImportError:  # pragma: no cover - documented fallback until requirements are installed
    OperationDefinitionNode = None
    parse = None


OPERATION_RE = re.compile(r"\b(query|mutation)\s+([A-Za-z_][A-Za-z0-9_]*)")
FIELD_RE = re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)")


def operation_info(query: str, explicit_name: str | None = None) -> tuple[str, str]:
    if parse is not None:
        document = parse(query)
        operations = [node for node in document.definitions if isinstance(node, OperationDefinitionNode)]
        selected = next(
            (node for node in operations if node.name and node.name.value == explicit_name),
            operations[0] if len(operations) == 1 else None,
        )
        if selected is not None:
            name = explicit_name or (selected.name.value if selected.name else selected.selection_set.selections[0].name.value)
            return selected.operation.value, name
    match = OPERATION_RE.search(query)
    if match:
        return match.group(1), explicit_name or match.group(2)
    field = FIELD_RE.search(query)
    return "query", explicit_name or (field.group(1) if field else "Unknown")


class GraphQLDispatcher:
    """Compatibility dispatcher. Aliases are expanded as captured operations are confirmed."""

    def __init__(self, store: ProjectStore):
        self.store = store

    @staticmethod
    def error(message: str, code: str = "BAD_USER_INPUT") -> dict[str, Any]:
        return {"errors": [{"message": message, "extensions": {"code": code}}]}

    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = payload.get("query") or ""
        variables = payload.get("variables") or {}
        try:
            kind, operation = operation_info(query, payload.get("operationName"))
            normalized = operation.casefold()
            if normalized in {"teases", "myteases", "listteases", "eosteases"}:
                projects = [self._tease(project) for project in self.store.list_projects()]
                if normalized == "teases":
                    return {"data": {"me": {"id": "local-user", "allTeases": projects, "__typename": "User"}}}
                return {"data": {operation: projects}}
            if normalized in {"tease", "eostease", "gettease", "loadtease"}:
                project_id = self._project_id(variables)
                field = "tease" if normalized == "loadtease" else operation
                return {"data": {field: self._tease(self.store.get_project(project_id), include_script=True)}}
            if normalized in {"createtease", "createeostease"}:
                raw_id = variables.get("id") or variables.get("slug")
                project_id = str(raw_id) if raw_id else self.store.next_numeric_project_id()
                created = self.store.create_project(
                    project_id,
                    str(variables.get("title") or project_id),
                    str(variables.get("author") or "Local Author"),
                    source_mode=str(variables.get("sourceMode") or "legacy-eos"),
                )
                return {"data": {"createTease": self._tease(created)}}
            if normalized == "uploadscriptpatches":
                project_id = self._project_id(variables, "teaseId")
                patches = variables.get("patches")
                if not isinstance(patches, list):
                    raise ValidationError("patches must be a list")
                self.store.apply_script_patches(project_id, patches)
                return {"data": {"patchEosScriptMultiple": {"id": project_id, "__typename": "EosTease"}}}
            if normalized in {"savetease", "saveeostease", "updatescript", "saveeosscript"}:
                project_id = self._project_id(variables)
                script = variables.get("script") or variables.get("eosscript") or variables.get("data")
                if isinstance(script, str):
                    script = json.loads(script)
                result = self.store.save_script(project_id, script)
                return {"data": {operation: {"id": project_id, **result}}}
            if normalized in {"updatetease", "renametease"}:
                project_id = self._project_id(variables)
                updated = self.store.update_project(project_id, variables.get("input") or variables)
                return {"data": {operation: self._tease(updated)}}
            if normalized == "deletetease":
                project_id = self._project_id(variables, "teaseId")
                self.store.delete_project(project_id)
                return {"data": {"deleteTease": True}}
            if normalized == "checkmediahash":
                media = self.store.find_media_by_hash(self._project_id(variables, "teaseId"), str(variables.get("hash") or "")) if variables.get("teaseId") else None
                # The official query does not send teaseId. Search local projects only.
                if media is None:
                    for project in self.store.list_projects():
                        media = self.store.find_media_by_hash(str(project["id"]), str(variables.get("hash") or ""))
                        if media is not None:
                            break
                if media is not None:
                    media = {key: media[key] for key in ("id", "mimeType", "size", "dimensions")}
                return {"data": {"mediaByHash": media}}
            if normalized == "addfiletotease":
                project_id = self._project_id(variables, "teaseId")
                media = self.store.find_media_by_hash(project_id, str(variables.get("hash") or ""))
                if media is None:
                    raise NotFoundError(str(variables.get("hash") or ""))
                result = {
                    "id": self.store._numeric_id(f"{media['hash']}:{variables.get('name', '')}"),
                    "name": str(variables.get("name") or media["hash"]),
                    "mediaHash": {key: media[key] for key in ("id", "hash", "size", "mimeType", "dimensions")},
                }
                return {"data": {"addFileToTease": result}}
            if normalized in {"media", "teasemedia", "listmedia", "files", "galleries"}:
                project_id = self._project_id(variables)
                return {"data": {operation: self.store.list_media(project_id, str(variables.get("query") or ""))}}
            if normalized in {"archivemedia", "deletemedia", "removefile"}:
                project_id = self._project_id(variables)
                result = self.store.archive_media(project_id, variables.get("path") or variables.get("file") or "")
                return {"data": {operation: {"success": True, **result}}}
            if normalized == "deletefiles":
                project_id = self._project_id(variables, "teaseId") if variables.get("teaseId") else self._find_project_for_media_ids(variables.get("files") or [])
                self.store.archive_media_ids(project_id, variables.get("files") or [])
                return {"data": {"deleteFiles": True}}
            if normalized in {"renamemedia", "renamefile"}:
                if normalized == "renamefile" and variables.get("fileId") is not None:
                    project_id = self._find_project_for_media_ids([variables["fileId"]])
                    self.store.rename_media_id(project_id, int(variables["fileId"]), str(variables.get("name") or ""))
                    return {"data": {"renameFile": True}}
                project_id = self._project_id(variables)
                result = self.store.rename_media(project_id, variables.get("path") or "", variables.get("name") or "")
                return {"data": {operation: {"success": True, **result}}}
            if normalized == "loadteasestorage":
                project_id = self._project_id(variables, "teaseId")
                return {"data": {"loadTeaseStorage": {"data": self.store.load_storage(project_id)}}}
            if normalized == "saveteasestorage":
                project_id = self._project_id(variables, "teaseId")
                self.store.save_storage(project_id, variables.get("data") or "{}")
                return {"data": {"saveTeaseStorage": True}}
            if normalized in {"publishtease", "ratetease"}:
                return self.error("Online publishing and rating are disabled in the local editor", "LOCAL_ONLY")
            return self.error(f"Unsupported local GraphQL operation: {operation}", "UNSUPPORTED_OPERATION")
        except GeneratedArtifactReadOnlyError as exc:
            return self.error(str(exc), exc.code)
        except (ValidationError, ValueError, TypeError) as exc:
            return self.error(str(exc))
        except NotFoundError as exc:
            return self.error(f"Not found: {exc}", "NOT_FOUND")
        except Exception as exc:
            return self.error(f"Local GraphQL error: {exc}", "INTERNAL_SERVER_ERROR")

    @staticmethod
    def _project_id(variables: dict[str, Any], preferred: str = "projectId") -> str:
        value = variables.get(preferred) or variables.get("id") or variables.get("teaseId")
        if value is None:
            raise ValidationError("A project id is required")
        return str(value)

    def _find_project_for_media_ids(self, media_ids: list[int]) -> str:
        wanted = {int(value) for value in media_ids}
        for project in self.store.list_projects():
            if any(int(item["id"]) in wanted for item in self.store.list_media(str(project["id"]))):
                return str(project["id"])
        raise NotFoundError("media")

    def _tease(self, project: dict[str, Any], include_script: bool = False) -> dict[str, Any]:
        project_id = str(project["id"])
        item = {
            "id": project_id,
            "title": project.get("title", project_id),
            "author": {"id": "local", "name": project.get("author", "Local Author")},
            "status": project.get("status", "draft"),
            "sourceMode": project.get("sourceMode", "legacy-eos"),
            "createdAt": project.get("createdAt"),
            "updatedAt": project.get("updatedAt"),
            "isPublished": False,
            "__typename": "EosTease",
        }
        if include_script:
            script = self.store.load_script(project_id)
            item["script"] = json.dumps(script, ensure_ascii=False, separators=(",", ":"))
            item["eosscript"] = script
            item["privateShareUrl"] = f"/preview/{project_id}/"
            item["thumbnail"] = None
        return item
