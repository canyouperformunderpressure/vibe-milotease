#!/usr/bin/env python3
"""Launch a supported agent with an explicitly user-supplied system prompt.

This project does not bundle a default or jailbreak prompt. The caller must
provide a non-empty UTF-8 text file explicitly with ``--source``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from init_system_prompt import DEFAULT_REPO_ROOT, normalize_agent


AGENT_COMMANDS = {
    "claude": "claude",
    "codex": "codex",
    "opencode": "opencode",
    "pi": "pi",
}

CLAUDE_PROMPT_FLAGS = {
    "--system-prompt",
    "--system-prompt-file",
    "--append-system-prompt",
    "--append-system-prompt-file",
}
PI_PROMPT_FLAGS = {
    "--system-prompt",
    "--append-system-prompt",
}
CODEX_CONFIG_FLAGS = {"-c", "--config"}


@dataclass(frozen=True)
class LaunchPlan:
    """A fully prepared process invocation without running it."""

    agent: str
    role: str
    command: tuple[str, ...]
    environment: Mapping[str, str]
    source_file: Path


def _flag_name(argument: str) -> str:
    return argument.split("=", 1)[0]


def _has_prompt_flag(arguments: Sequence[str], flags: set[str]) -> bool:
    return any(_flag_name(argument) in flags for argument in arguments)


def _has_codex_developer_override(arguments: Sequence[str]) -> bool:
    for index, argument in enumerate(arguments):
        if argument in CODEX_CONFIG_FLAGS and index + 1 < len(arguments):
            value = arguments[index + 1]
            if value.split("=", 1)[0].strip() == "developer_instructions":
                return True
        if argument.startswith(("-c", "--config")) and "=" in argument:
            value = argument.split("=", 1)[1]
            if value.split("=", 1)[0].strip() == "developer_instructions":
                return True
    return False


def _toml_basic_string(value: str) -> str:
    """Encode a string as a TOML basic string for Codex ``-c``."""

    return json.dumps(value, ensure_ascii=False)


def _default_executable(agent: str) -> str:
    """Prefer Windows ``.cmd`` shims over PowerShell-only npm wrappers."""

    command = AGENT_COMMANDS[agent]
    if os.name == "nt" and agent in {"codex", "opencode"}:
        command = f"{command}.cmd"
    return shutil.which(command) or command


def _default_command_prefix(agent: str) -> tuple[str, ...]:
    """Return an executable prefix that is safe for arbitrary prompt text."""

    executable = _default_executable(agent)
    if agent == "codex" and os.name == "nt" and executable.lower().endswith(".cmd"):
        shim = Path(executable)
        script = shim.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node")
        if node and script.is_file():
            return (node, str(script))
    return (executable,)


def _opencode_environment(
    source_file: Path,
    base_environment: Mapping[str, str],
) -> dict[str, str]:
    """Add an OpenCode instruction overlay without touching project config."""

    existing_raw = base_environment.get("OPENCODE_CONFIG_CONTENT")
    if existing_raw:
        try:
            existing = json.loads(existing_raw)
        except json.JSONDecodeError as exc:
            raise ValueError("OPENCODE_CONFIG_CONTENT is not valid JSON") from exc
        if not isinstance(existing, dict):
            raise ValueError("OPENCODE_CONFIG_CONTENT must contain a JSON object")
        overlay = dict(existing)
    else:
        overlay = {}

    instructions = overlay.get("instructions", [])
    if not isinstance(instructions, list) or not all(isinstance(item, str) for item in instructions):
        raise ValueError("OPENCODE_CONFIG_CONTENT.instructions must be a string list")

    source_path = source_file.as_posix()
    if source_path not in instructions:
        instructions.append(source_path)
    overlay["instructions"] = instructions

    environment = dict(base_environment)
    environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(overlay, ensure_ascii=False)
    return environment


def _read_prompt(source_file: Path) -> tuple[Path, str]:
    source = source_file.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"system prompt source not found: {source}")
    prompt = source.read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError(f"system prompt source is empty: {source}")
    return source, prompt


def build_launch_plan(
    agent: str,
    source_file: Path,
    forwarded: Sequence[str] = (),
    executable: str | None = None,
    base_environment: Mapping[str, str] | None = None,
) -> LaunchPlan:
    """Build a launch plan using only the explicitly supplied prompt file."""

    canonical = normalize_agent(agent)
    source, prompt = _read_prompt(source_file)
    arguments = tuple(forwarded)
    environment = dict(os.environ if base_environment is None else base_environment)
    command_prefix = (executable,) if executable else _default_command_prefix(canonical)

    if canonical == "claude":
        if _has_prompt_flag(arguments, CLAUDE_PROMPT_FLAGS):
            raise ValueError("Claude prompt flags are managed by the launcher; remove the forwarded prompt flag")
        command = (*command_prefix, "--append-system-prompt-file", str(source), *arguments)
        return LaunchPlan(canonical, "system", command, environment, source)

    if canonical == "codex":
        if _has_codex_developer_override(arguments):
            raise ValueError("Codex developer_instructions is managed by the launcher; remove the forwarded override")
        override = f"developer_instructions={_toml_basic_string(prompt)}"
        command = (*command_prefix, "-c", override, *arguments)
        return LaunchPlan(canonical, "developer", command, environment, source)

    if canonical == "opencode":
        environment = _opencode_environment(source, environment)
        command = (*command_prefix, *arguments)
        return LaunchPlan(canonical, "system", command, environment, source)

    if _has_prompt_flag(arguments, PI_PROMPT_FLAGS):
        raise ValueError("Pi prompt flags are managed by the launcher; remove the forwarded prompt flag")
    command = (*command_prefix, "--append-system-prompt", prompt, *arguments)
    return LaunchPlan(canonical, "system", command, environment, source)


def _display_plan(plan: LaunchPlan) -> None:
    """Print a safe dry-run representation without leaking prompt contents."""

    payload = {
        "agent": plan.agent,
        "role": plan.role,
        "source": str(plan.source_file),
        "command": list(plan.command),
    }
    if plan.agent == "opencode":
        try:
            config = json.loads(plan.environment["OPENCODE_CONFIG_CONTENT"])
            payload["OPENCODE_CONFIG_CONTENT"] = config
        except (KeyError, json.JSONDecodeError):
            payload["OPENCODE_CONFIG_CONTENT"] = "<invalid>"
    elif plan.agent == "codex":
        command = list(plan.command)
        config_index = command.index("-c")
        command[config_index + 1] = "developer_instructions=<user-supplied source contents>"
        payload["command"] = command
    elif plan.agent == "pi":
        command = list(plan.command)
        prompt_index = command.index("--append-system-prompt")
        command[prompt_index + 1] = "<user-supplied source contents>"
        payload["command"] = command
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Launch Claude, Codex, OpenCode, or Pi with a user-supplied system prompt."
    )
    parser.add_argument("--agent", required=True, help="claude, codex, opencode, or pi")
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="path to a non-empty UTF-8 prompt file supplied by the user",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="working/project root for the launched agent (default: this checkout)",
    )
    parser.add_argument("--executable", help="override the agent executable for testing or a custom installation")
    parser.add_argument("--dry-run", action="store_true", help="print the prepared invocation without launching")
    parser.add_argument("agent_args", nargs=argparse.REMAINDER, help="arguments passed to the selected agent after --")
    args = parser.parse_args(argv)

    forwarded = list(args.agent_args)
    if forwarded and forwarded[0] == "--":
        forwarded.pop(0)

    try:
        plan = build_launch_plan(
            args.agent,
            source_file=args.source,
            forwarded=forwarded,
            executable=args.executable,
        )
        repo_root = args.repo_root.resolve()
        if not repo_root.is_dir():
            raise NotADirectoryError(f"repository root not found: {repo_root}")
        if args.dry_run:
            _display_plan(plan)
            return 0
        completed = subprocess.run(plan.command, cwd=repo_root, env=dict(plan.environment), check=False)
        return completed.returncode
    except (FileNotFoundError, NotADirectoryError, OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
