from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

import yaml

from .models import Action, MiloSourceError, SourceBundle, SourceIssue
from .parser import JsonSafeLoader


PRIORITIES = {"main", "side", "fail"}
PICK_TYPES = {"sequence", "random", "first"}
DURATION_RE = re.compile(r"^(?:(?:\d+(?:\.\d+)?)h)?(?:(?:\d+(?:\.\d+)?)m)?(?:(?:\d+(?:\.\d+)?)s)?(?:(?:\d+(?:\.\d+)?)ms)?$")
SET_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(=|\+=|-=|\*=|/=)\s*(.+?)\s*$", re.DOTALL)


@dataclass(frozen=True)
class Expr:
    kind: str
    value: Any = None
    children: tuple["Expr", ...] = ()


@dataclass(frozen=True)
class SetExpr:
    target: str
    operator: str
    value: Any
    value_is_state: bool = False


TOKEN_RE = re.compile(
    r"\s*(?:(?P<number>-?(?:0|[1-9]\d*)(?:\.\d+)?)|"
    r"(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:''|[^'])*')|"
    r"(?P<op>==|!=|>=|<=|>|<)|(?P<lparen>\()|(?P<rparen>\))|"
    r"(?P<ident>[A-Za-z_][A-Za-z0-9_]*))"
)


def _issue(level: str, code: str, message: str, path: str = "") -> SourceIssue:
    return SourceIssue(level, code, message, path)


def _parse_string_token(token: str) -> str:
    if token.startswith('"'):
        return json.loads(token)
    # YAML single-quoted strings escape a quote by doubling it.
    return token[1:-1].replace("''", "'")


def _tokenize_condition(text: str, path: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    position = 0
    while position < len(text):
        match = TOKEN_RE.match(text, position)
        if not match:
            raise MiloSourceError([_issue("error", "CONDITION_TOKEN", "The condition contains unsupported characters or syntax.", path)])
        position = match.end()
        kind = match.lastgroup or ""
        raw = match.group(kind)
        if kind == "number":
            value: Any = float(raw) if "." in raw else int(raw)
            tokens.append(("literal", value))
        elif kind == "string":
            tokens.append(("literal", _parse_string_token(raw)))
        elif kind == "ident" and raw in {"true", "false", "null"}:
            tokens.append(("literal", {"true": True, "false": False, "null": None}[raw]))
        elif kind == "ident" and raw in {"and", "or", "not"}:
            tokens.append((raw, raw))
        else:
            tokens.append((kind, raw))
    return tokens


class _ConditionParser:
    def __init__(self, tokens: list[tuple[str, Any]], path: str):
        self.tokens = tokens
        self.path = path
        self.index = 0

    def current(self) -> tuple[str, Any] | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def accept(self, kind: str) -> tuple[str, Any] | None:
        token = self.current()
        if token and token[0] == kind:
            self.index += 1
            return token
        return None

    def expect(self, kind: str) -> tuple[str, Any]:
        token = self.accept(kind)
        if token is None:
            raise MiloSourceError([_issue("error", "CONDITION_SYNTAX", f"The condition requires {kind}。", self.path)])
        return token

    def parse(self) -> Expr:
        if not self.tokens:
            raise MiloSourceError([_issue("error", "CONDITION_EMPTY", "The condition cannot be empty.", self.path)])
        result = self.parse_or()
        if self.current() is not None:
            raise MiloSourceError([_issue("error", "CONDITION_TRAILING", "The condition has trailing content.", self.path)])
        return result

    def parse_or(self) -> Expr:
        left = self.parse_and()
        while self.accept("or"):
            left = Expr("or", children=(left, self.parse_and()))
        return left

    def parse_and(self) -> Expr:
        left = self.parse_not()
        while self.accept("and"):
            left = Expr("and", children=(left, self.parse_not()))
        return left

    def parse_not(self) -> Expr:
        if self.accept("not"):
            return Expr("not", children=(self.parse_not(),))
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        if self.accept("lparen"):
            value = self.parse_or()
            self.expect("rparen")
            return value
        left = self.parse_operand()
        operator = self.accept("op")
        if operator:
            return Expr("compare", value=operator[1], children=(left, self.parse_operand()))
        return left

    def parse_operand(self) -> Expr:
        token = self.current()
        if token is None or token[0] not in {"ident", "literal"}:
            raise MiloSourceError([_issue("error", "CONDITION_OPERAND", "The condition requires a state name or literal value.", self.path)])
        self.index += 1
        return Expr("state" if token[0] == "ident" else "literal", value=token[1])


def parse_condition(text: Any, path: str = "condition") -> Expr:
    if not isinstance(text, str):
        raise MiloSourceError([_issue("error", "CONDITION_TYPE", "The condition must be a string.", path)])
    return _ConditionParser(_tokenize_condition(text, path), path).parse()


def condition_state_refs(expr: Expr) -> set[str]:
    refs = {str(expr.value)} if expr.kind == "state" else set()
    for child in expr.children:
        refs.update(condition_state_refs(child))
    return refs


def condition_to_js(expr: Expr) -> str:
    if expr.kind == "state":
        return f"__milo_state[{json.dumps(expr.value, ensure_ascii=False)}]"
    if expr.kind == "literal":
        return json.dumps(expr.value, ensure_ascii=False, separators=(",", ":"))
    if expr.kind == "compare":
        operator = "===" if expr.value == "==" else "!==" if expr.value == "!=" else expr.value
        return f"({condition_to_js(expr.children[0])} {operator} {condition_to_js(expr.children[1])})"
    if expr.kind in {"and", "or"}:
        operator = "&&" if expr.kind == "and" else "||"
        return f"({condition_to_js(expr.children[0])} {operator} {condition_to_js(expr.children[1])})"
    if expr.kind == "not":
        return f"!({condition_to_js(expr.children[0])})"
    raise ValueError(f"Unknown expression kind: {expr.kind}")


def parse_set(value: Any, state_ids: set[str], path: str = "set") -> SetExpr:
    if isinstance(value, str):
        match = SET_RE.fullmatch(value)
        if not match:
            raise MiloSourceError([_issue("error", "SET_SYNTAX", "set must look like score += 1.", path)])
        target, operator, raw_value = match.groups()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", raw_value) and raw_value in state_ids:
            return SetExpr(target, operator, raw_value, True)
        quoted = raw_value.startswith(("\"", "'"))
        if not quoted and re.search(r"[;`(){}\[\]]", raw_value):
            raise MiloSourceError([_issue("error", "SET_CODE_REJECTED", "The right-hand side of set cannot contain code or function calls.", path)])
        try:
            parsed = yaml.load(raw_value, Loader=JsonSafeLoader)
        except yaml.YAMLError as exc:
            raise MiloSourceError([_issue("error", "SET_VALUE", "The right-hand side of set is not a safe literal value.", path)]) from exc
        if isinstance(parsed, (dict, list)):
            raise MiloSourceError([_issue("error", "SET_VALUE", "The right-hand side of set must be a state name or scalar literal.", path)])
        return SetExpr(target, operator, parsed, False)
    if isinstance(value, dict):
        allowed = {"variable", "op", "value"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise MiloSourceError([_issue("error", "SET_FIELD", f"set does not support fields: {', '.join(unknown)}", path)])
        target = value.get("variable")
        operator = value.get("op", "=")
        raw_value = value.get("value")
        if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target):
            raise MiloSourceError([_issue("error", "SET_TARGET", "set.variable must be a state ID.", path)])
        if operator not in {"=", "+=", "-=", "*=", "/="}:
            raise MiloSourceError([_issue("error", "SET_OPERATOR", "set.op is not supported.", path)])
        if isinstance(raw_value, (dict, list)):
            raise MiloSourceError([_issue("error", "SET_VALUE", "set.value must be a state name or scalar.", path)])
        is_state = isinstance(raw_value, str) and raw_value in state_ids
        return SetExpr(target, operator, raw_value, is_state)
    raise MiloSourceError([_issue("error", "SET_TYPE", "set must be an expression string or object.", path)])


def set_to_js(expr: SetExpr) -> str:
    target = f"__milo_state[{json.dumps(expr.target, ensure_ascii=False)}]"
    value = (
        f"__milo_state[{json.dumps(expr.value, ensure_ascii=False)}]"
        if expr.value_is_state
        else json.dumps(expr.value, ensure_ascii=False, separators=(",", ":"))
    )
    return f"{target} {expr.operator} {value};"


def normalize_target(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MiloSourceError([_issue("error", "TARGET_TYPE", "Targets must be non-empty strings.", path)])
    target = value.strip()
    if target.startswith("$") and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,119}", target[1:]):
        raise MiloSourceError([_issue("error", "TARGET_ID", "The Outline node target ID is invalid.", path)])
    return target


def normalize_choices(value: Any, path: str) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for label, target in value.items():
            if not isinstance(label, str) or not label.strip():
                raise MiloSourceError([_issue("error", "CHOICE_LABEL", "choice labels must be non-empty strings.", path)])
            choices.append({"label": label, "target": normalize_target(target, path), "payload": {"label": label}})
    elif isinstance(value, list):
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                raise MiloSourceError([_issue("error", "CHOICE_SHAPE", "Long-form choice options must be objects.", item_path)])
            label = item.get("label")
            if not isinstance(label, str) or not label.strip():
                raise MiloSourceError([_issue("error", "CHOICE_LABEL", "choice.label must be a non-empty string.", item_path)])
            color = item.get("color")
            if color is not None and not isinstance(color, str):
                raise MiloSourceError([_issue("error", "CHOICE_COLOR", "choice.color must be a string.", item_path)])
            payload = dict(item)
            payload.pop("to", None)
            choices.append({"label": label, "target": normalize_target(item.get("to"), item_path), "payload": payload})
    else:
        raise MiloSourceError([_issue("error", "CHOICE_TYPE", "choice must be a label-to-target object or a long-form list.", path)])
    if not choices:
        raise MiloSourceError([_issue("error", "CHOICE_EMPTY", "choice requires at least one option.", path)])
    return choices


def normalize_if(value: Any, path: str) -> tuple[list[tuple[str, str]], str | None]:
    if not isinstance(value, dict) or not value:
        raise MiloSourceError([_issue("error", "IF_TYPE", "if must be a condition-to-target object.", path)])
    branches: list[tuple[str, str]] = []
    fallback: str | None = None
    for condition, target in value.items():
        if condition == "else":
            if fallback is not None:
                raise MiloSourceError([_issue("error", "IF_ELSE", "if may contain only one else branch.", path)])
            fallback = normalize_target(target, f"{path}.else")
            continue
        if not isinstance(condition, str):
            raise MiloSourceError([_issue("error", "IF_CONDITION", "if condition keys must be strings.", path)])
        branches.append((condition, normalize_target(target, path)))
    if not branches:
        raise MiloSourceError([_issue("error", "IF_EMPTY", "if requires at least one conditional branch.", path)])
    return branches, fallback


def normalize_random(value: Any, path: str) -> list[tuple[str, float]]:
    if not isinstance(value, dict) or not value:
        raise MiloSourceError([_issue("error", "RANDOM_TYPE", "random must be a target-to-weight object.", path)])
    branches: list[tuple[str, float]] = []
    for target, weight in value.items():
        normalized = normalize_target(target, path)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            raise MiloSourceError([_issue("error", "RANDOM_WEIGHT", "random weights must be positive numbers.", path)])
        branches.append((normalized, float(weight)))
    return branches


def normalize_asset_reference(value: Any, path: str) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value.strip():
        raise MiloSourceError([_issue("error", "ASSET_REFERENCE", "Media references must be non-empty strings.", path)])
    raw = value.strip().replace("\\", "/")
    asset_id, separator, selector = raw.partition("/")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,119}", asset_id):
        raise MiloSourceError([_issue("error", "ASSET_REFERENCE", "Asset ID is invalid.", path)])
    return asset_id, selector if separator else None


KNOWN_EOS_COMMANDS = {
    "say", "image", "audio", "audio.play", "wait", "timer", "goto",
    "choice", "if", "random", "set", "eval", "prompt", "notification",
    "notification.create", "notification.remove", "enable", "disable", "end", "noop", "storage",
    "preload",
}


def _is_raw_action(action: Action) -> bool:
    value = action.value
    if action.kind in {"say", "image", "prompt"}:
        # EOS commands use mapping payloads. Mapping always wins over Milo
        # shorthand so current and future EOS fields cannot be reinterpreted.
        return isinstance(value, dict)
    if action.kind == "timer":
        return isinstance(value, dict)
    if action.kind == "goto":
        return isinstance(value, dict)
    if action.kind in {"enable", "disable"}:
        return isinstance(value, dict)
    if action.kind == "choice":
        return isinstance(value, dict) and "options" in value
    if action.kind == "if":
        return isinstance(value, dict) and bool({"condition", "commands", "elseCommands"} & set(value))
    if action.kind == "end":
        return isinstance(value, dict)
    return action.kind not in {"audio", "wait", "random", "set", "notification", "preload"}


SHORTHAND_FIELDS = {
    "audio": {"asset", "action", "volume", "loops", "locator", "background", "id"},
    "notification": {
        "id", "title", "button", "button_label", "to", "remove",
        "buttonLabel", "buttonCommands", "timerDuration", "timerCommands",
    },
    "wait": {"duration", "style", "isAsync", "commands"},
    "preload": {"to", "scope", "message", "button", "notification", "id", "bar_width"},
}

RAW_EOS_PAYLOAD_FIELDS = {
    "image": {"locator"},
    "say": {"label", "mode", "align", "duration", "allowSkip", "visible", "disableTyping"},
    "goto": {"target"},
    "timer": {"duration", "style", "isAsync", "commands"},
    "choice": {"options"},
    "end": set(),
    "prompt": {"variable"},
    "eval": {"script"},
    "if": {"condition", "commands", "elseCommands"},
    "enable": {"target"},
    "disable": {"target"},
    "notification.create": {"id", "title", "buttonLabel", "buttonCommands", "timerDuration", "timerCommands"},
    "notification.remove": {"id"},
    "audio.play": {"locator", "background", "volume", "loops", "id"},
}


def _shorthand_extra_fields(action: Action) -> tuple[str, ...]:
    if _is_raw_action(action) or not isinstance(action.value, dict):
        if action.kind == "choice" and isinstance(action.value, list):
            return tuple(
                f"[{index}].{field}"
                for index, item in enumerate(action.value)
                if isinstance(item, dict)
                for field in sorted(set(item) - {"label", "to", "color", "commands"})
            )
        return ()
    allowed = SHORTHAND_FIELDS.get(action.kind)
    if allowed is None:
        return ()
    return tuple(sorted(set(action.value) - allowed))


def _raw_eos_extra_fields(action: Action) -> tuple[str, ...]:
    if not _is_raw_action(action) or not isinstance(action.value, dict):
        return ()
    allowed = RAW_EOS_PAYLOAD_FIELDS.get(action.kind)
    if allowed is None:
        return ()
    fields = [field for field in sorted(set(action.value) - allowed)]
    if action.kind == "choice" and isinstance(action.value.get("options"), list):
        for index, option in enumerate(action.value["options"]):
            if isinstance(option, dict):
                fields.extend(
                    f"options[{index}].{field}"
                    for field in sorted(set(option) - {"label", "color", "visible", "target", "commands"})
                )
    return tuple(fields)


def _targets_from_commands(commands: Any) -> list[str]:
    targets: list[str] = []
    if not isinstance(commands, list):
        return targets
    for command in commands:
        if not isinstance(command, dict) or len(command) != 1:
            continue
        kind, payload = next(iter(command.items()))
        if kind == "goto" and isinstance(payload, dict) and isinstance(payload.get("target"), str):
            targets.append(payload["target"])
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key == "options" and isinstance(value, list):
                    for option in value:
                        if isinstance(option, dict):
                            if isinstance(option.get("target"), str):
                                targets.append(option["target"])
                            targets.extend(_targets_from_commands(option.get("commands")))
                elif key.endswith("Commands") or key in {"commands", "elseCommands"}:
                    targets.extend(_targets_from_commands(value))
    return targets


def _action_targets(action: Action) -> list[str]:
    if _is_raw_action(action):
        return _targets_from_commands([{action.kind: action.value}])
    if action.kind == "goto":
        return [normalize_target(action.value, action.path)]
    if action.kind == "choice":
        return [item["target"] for item in normalize_choices(action.value, action.path)]
    if action.kind == "if":
        branches, fallback = normalize_if(action.value, action.path)
        return [target for _, target in branches] + ([fallback] if fallback else [])
    if action.kind == "random":
        return [target for target, _ in normalize_random(action.value, action.path)]
    if action.kind == "notification" and isinstance(action.value, dict) and action.value.get("to"):
        return [normalize_target(action.value["to"], action.path)]
    if action.kind == "preload" and isinstance(action.value, dict):
        return [normalize_target(action.value.get("to"), action.path)]
    return []


def validate_bundle(bundle: SourceBundle) -> tuple[SourceIssue, ...]:
    issues: list[SourceIssue] = []
    outline = bundle.outline
    runtime = bundle.runtime
    node_ids = set(outline.nodes)
    state_ids = set(runtime.state)

    for field in runtime.unknown_fields:
        issues.append(_issue("warning", "EOS_ROOT_UNKNOWN", f"Unrecognized EOS top-level field will be preserved unchanged: {field}", f"milo.yaml.{field}"))

    if outline.entry not in node_ids:
        issues.append(_issue("error", "OUTLINE_ENTRY", "entry does not point to an existing node.", "outline.yaml.entry"))
    for node_id, node in outline.nodes.items():
        seen_targets: set[str] = set()
        for index, edge in enumerate(node.next):
            path = f"outline.yaml.nodes.{node_id}.next[{index}]"
            if edge.target not in node_ids:
                issues.append(_issue("error", "OUTLINE_EDGE_TARGET", f"Exit target does not exist: {edge.target}", path))
            if edge.priority not in PRIORITIES:
                issues.append(_issue("error", "OUTLINE_PRIORITY", "priority must be main, side, or fail.", path))
            if edge.target in seen_targets:
                issues.append(_issue("warning", "OUTLINE_EDGE_DUPLICATE", f"The same node points repeatedly to {edge.target}。", path))
            seen_targets.add(edge.target)

    if outline.entry in node_ids:
        reached: set[str] = set()
        queue = [outline.entry]
        while queue:
            current = queue.pop(0)
            if current in reached or current not in outline.nodes:
                continue
            reached.add(current)
            queue.extend(edge.target for edge in outline.nodes[current].next)
        for node_id in node_ids - reached:
            issues.append(_issue("warning", "OUTLINE_UNREACHABLE", "Unreachable from entry.", f"outline.yaml.nodes.{node_id}"))
    if not any(not node.next for node in outline.nodes.values()):
        issues.append(_issue("warning", "OUTLINE_NO_TERMINAL", "The Outline has no terminal node without exits.", "outline.yaml.nodes"))

    for asset_id, asset in runtime.assets.items():
        if asset.pick not in PICK_TYPES:
            issues.append(_issue("error", "ASSET_PICK", "pick must be sequence, random, or first.", f"milo.yaml.assets.{asset_id}.pick"))
        if asset.media_type is not None and asset.media_type not in {"image", "audio"}:
            issues.append(_issue("error", "ASSET_TYPE", "type must be image or audio.", f"milo.yaml.assets.{asset_id}.type"))

    missing_scenes = node_ids - set(bundle.scenes)
    extra_scenes = set(bundle.scenes) - node_ids
    for scene_id in sorted(missing_scenes):
        issues.append(_issue("error", "IR_SCENE_MISSING", "Outline node is missing its corresponding Milo IR.", f"src/{scene_id}.milo.yaml"))
    for scene_id in sorted(extra_scenes):
        issues.append(_issue("error", "IR_SCENE_EXTRA", "Milo IR scene does not correspond to any Outline node.", f"src/{scene_id}.milo.yaml"))

    page_owner: dict[str, str] = {}
    for scene_id, scene in bundle.scenes.items():
        for page_id in scene.pages:
            previous = page_owner.get(page_id)
            if previous is not None:
                issues.append(_issue("error", "IR_PAGE_DUPLICATE", f"Duplicate global Page ID: {page_id} (also present in {previous}).", f"src/{scene_id}.milo.yaml.pages.{page_id}"))
            else:
                page_owner[page_id] = scene_id
    if "start" in page_owner and page_owner["start"] != outline.entry:
        issues.append(_issue("error", "IR_START_OWNER", "An explicit start Page must belong to the Outline entry node.", f"src/{page_owner['start']}.milo.yaml.pages.start"))

    for scene_id, scene in bundle.scenes.items():
        if scene.entry not in scene.pages:
            issues.append(_issue("error", "IR_ENTRY", "entry Page does not exist.", f"src/{scene_id}.milo.yaml.entry"))
        outline_node = outline.nodes.get(scene_id)
        allowed_external = {edge.target for edge in outline_node.next} if outline_node else set()
        local_adjacency: dict[str, list[str]] = {page_id: [] for page_id in scene.pages}
        for page_id, page in scene.pages.items():
            for action in page.actions:
                raw_action = _is_raw_action(action)
                if action.kind == "audio.stop":
                    issues.append(_issue("error", "EOS_COMMAND_UNSUPPORTED", "The current EOS Runtime does not support audio.stop; use the audio shorthand with action: stop + id, or eval to call Sound.get(id).stop().", action.path))
                elif action.kind not in KNOWN_EOS_COMMANDS:
                    issues.append(_issue("warning", "EOS_COMMAND_UNKNOWN", f"Unrecognized EOS command will be preserved unchanged: {action.kind}", action.path))
                for field in _shorthand_extra_fields(action):
                    field_path = f"{action.path}{field}" if field.startswith("[") else f"{action.path}.{field}"
                    issues.append(_issue("warning", "EOS_PAYLOAD_UNKNOWN", f"Unrecognized shorthand payload field will be preserved unchanged: {field}", field_path))
                for field in _raw_eos_extra_fields(action):
                    issues.append(_issue("warning", "EOS_PAYLOAD_UNKNOWN", f"Unrecognized EOS payload field will be preserved unchanged: {field}", f"{action.path}.{field}"))
                try:
                    targets = _action_targets(action)
                except MiloSourceError as exc:
                    issues.extend(exc.issues)
                    targets = []
                for target in targets:
                    if target.startswith("$") and not raw_action:
                        external = target[1:]
                        if external not in allowed_external:
                            issues.append(_issue("error", "IR_EXTERNAL_NOT_ALLOWED", f"Outline does not allow this cross-node exit: {target}", action.path))
                    elif target not in page_owner:
                        wildcard_matches = sorted(page for page in page_owner if "*" in target and fnmatch.fnmatch(page, target))
                        if wildcard_matches:
                            local_adjacency[page_id].extend(page for page in wildcard_matches if page_owner[page] == scene_id)
                        elif raw_action:
                            issues.append(_issue("warning", "EOS_DYNAMIC_TARGET", f"Raw EOS goto target cannot be resolved statically: {target}", action.path))
                        else:
                            issues.append(_issue("error", "IR_PAGE_TARGET", f"Page does not exist: {target}", action.path))
                    elif page_owner[target] != scene_id:
                        external_scene = page_owner[target]
                        if external_scene not in allowed_external:
                            issues.append(_issue("error", "IR_EXTERNAL_NOT_ALLOWED", f"Outline does not allow this cross-node exit: {external_scene}", action.path))
                    else:
                        local_adjacency[page_id].append(target)
                try:
                    _validate_action_value(action, runtime.assets, state_ids)
                except MiloSourceError as exc:
                    issues.extend(exc.issues)
        if scene.entry in scene.pages:
            reached_pages: set[str] = set()
            queue = [scene.entry]
            while queue:
                current = queue.pop(0)
                if current in reached_pages:
                    continue
                reached_pages.add(current)
                queue.extend(local_adjacency.get(current, []))
            for page_id in set(scene.pages) - reached_pages:
                issues.append(_issue("warning", "IR_PAGE_UNREACHABLE", "Unreachable from scene entry.", f"src/{scene_id}.milo.yaml.pages.{page_id}"))

    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        raise MiloSourceError(issues)
    return tuple(issue for issue in issues if issue.level == "warning")


def _validate_action_value(action: Action, assets: dict[str, Any], state_ids: set[str]) -> None:
    value = action.value
    path = action.path
    if _is_raw_action(action):
        return
    if action.kind == "say":
        if isinstance(value, str):
            if not value.strip():
                raise MiloSourceError([_issue("error", "SAY_EMPTY", "say cannot be empty.", path)])
            return
        if not isinstance(value, dict) or not isinstance(value.get("text"), str) or not value["text"].strip():
            raise MiloSourceError([_issue("error", "SAY_SHAPE", "say shorthand must contain non-empty text.", path)])
        return
    if action.kind == "image":
        reference = value
        if isinstance(value, dict):
            if value.get("locator"):
                locator = value["locator"]
                if not isinstance(locator, str) or not locator.startswith(("file:", "gallery:")):
                    raise MiloSourceError([_issue("error", "IMAGE_LOCATOR", "image.locator must be a file: or gallery: locator.", path)])
                return
            reference = value.get("asset") or value.get("file")
        if not isinstance(reference, str) or not reference.strip():
            raise MiloSourceError([_issue("error", "ASSET_REFERENCE", "Media references must be non-empty strings.", path)])
        return
    if action.kind == "audio":
        reference = value
        if isinstance(value, dict):
            operation = value.get("action", "play")
            if operation not in {"play", "stop"}:
                raise MiloSourceError([_issue("error", "AUDIO_ACTION", "audio.action must be play or stop.", path)])
            if operation == "stop":
                sound_id = value.get("id")
                if not isinstance(sound_id, str) or not sound_id.strip():
                    raise MiloSourceError([_issue("error", "AUDIO_STOP_ID", "audio.action=stop requires a non-empty id for Sound.get(id).stop().", path)])
                return
            volume = value.get("volume", 1)
            loops = value.get("loops", 1)
            if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 1:
                raise MiloSourceError([_issue("error", "AUDIO_VOLUME", "audio.volume must be between 0 and 1.", path)])
            if isinstance(loops, bool) or not isinstance(loops, int) or loops < 0:
                raise MiloSourceError([_issue("error", "AUDIO_LOOPS", "audio.loops must be a non-negative integer.", path)])
            if value.get("locator"):
                if not isinstance(value["locator"], str) or not value["locator"].startswith("file:"):
                    raise MiloSourceError([_issue("error", "AUDIO_LOCATOR", "audio.locator must be a file: locator.", path)])
                return
            reference = value.get("asset")
        if not isinstance(reference, str) or not reference.strip():
            raise MiloSourceError([_issue("error", "ASSET_REFERENCE", "Media references must be non-empty strings.", path)])
        return
    if action.kind in {"wait", "timer"}:
        duration = value.get("duration") if isinstance(value, dict) else value
        if isinstance(duration, bool) or not isinstance(duration, (str, int, float)):
            raise MiloSourceError([_issue("error", "WAIT_DURATION", "wait must be a duration such as 30s.", path)])
        if isinstance(duration, (int, float)):
            if duration <= 0:
                raise MiloSourceError([_issue("error", "WAIT_DURATION", "wait must be greater than 0.", path)])
        elif not duration or not DURATION_RE.fullmatch(duration) or not re.search(r"\d", duration):
            raise MiloSourceError([_issue("error", "WAIT_DURATION", "wait has an invalid duration format.", path)])
        return
    if action.kind == "goto":
        normalize_target(value, path)
        return
    if action.kind in {"enable", "disable"}:
        normalize_target(value, path)
        return
    if action.kind == "choice":
        normalize_choices(value, path)
        return
    if action.kind == "if":
        branches, _ = normalize_if(value, path)
        for condition, _ in branches:
            expr = parse_condition(condition, path)
            unknown = condition_state_refs(expr) - state_ids
            if unknown:
                raise MiloSourceError([_issue("error", "STATE_UNKNOWN", f"Condition references undeclared state: {', '.join(sorted(unknown))}", path)])
        return
    if action.kind == "random":
        normalize_random(value, path)
        return
    if action.kind == "set":
        expression = parse_set(value, state_ids, path)
        if expression.target not in state_ids:
            raise MiloSourceError([_issue("error", "STATE_UNKNOWN", f"set target is undeclared: {expression.target}", path)])
        return
    if action.kind == "prompt":
        variable = value if isinstance(value, str) else value.get("variable") if isinstance(value, dict) else None
        if not isinstance(variable, str) or variable not in state_ids:
            raise MiloSourceError([_issue("error", "PROMPT_STATE", "prompt must reference a declared state variable.", path)])
        return
    if action.kind == "notification":
        if isinstance(value, str):
            if not value.strip():
                raise MiloSourceError([_issue("error", "NOTIFICATION_EMPTY", "notification cannot be empty.", path)])
            return
        if not isinstance(value, dict):
            raise MiloSourceError([_issue("error", "NOTIFICATION_SHAPE", "notification shorthand must be a string or object.", path)])
        if value.get("remove") is not None and not isinstance(value.get("remove"), str):
            raise MiloSourceError([_issue("error", "NOTIFICATION_REMOVE", "notification.remove must be a notification ID.", path)])
        return
    if action.kind == "preload":
        if not isinstance(value, dict):
            raise MiloSourceError([_issue("error", "PRELOAD_SHAPE", "preload must be an object.", path)])
        normalize_target(value.get("to"), path)
        scope = value.get("scope", "all")
        if scope != "all":
            raise MiloSourceError([_issue("error", "PRELOAD_SCOPE", "preload.scope currently supports only all.", path)])
        for field in ("message", "button", "notification", "id"):
            field_value = value.get(field)
            if field_value is not None and (not isinstance(field_value, str) or not field_value.strip()):
                raise MiloSourceError([_issue("error", "PRELOAD_FIELD", f"preload.{field} must be a non-empty string.", path)])
        bar_width = value.get("bar_width", 10)
        if isinstance(bar_width, bool) or not isinstance(bar_width, int) or not 1 <= bar_width <= 40:
            raise MiloSourceError([_issue("error", "PRELOAD_BAR_WIDTH", "preload.bar_width must be an integer from 1 to 40.", path)])
        return
    if action.kind == "end":
        if value is not None and value is not True and not isinstance(value, dict):
            raise MiloSourceError([_issue("error", "END_SHAPE", "end must use true or an empty object.", path)])
        return
    return
