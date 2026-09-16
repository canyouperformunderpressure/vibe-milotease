#!/usr/bin/env python3
"""Install a user-supplied system prompt for one supported coding agent.

This project does not bundle a default or jailbreak prompt. The caller must
provide a non-empty UTF-8 text file explicitly with ``--source``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = SCRIPT_DIR.parents[2]
LAUNCHER_PS1 = SCRIPT_DIR / "run-system-agent.ps1"
LAUNCHER_SH = SCRIPT_DIR / "run-system-agent.sh"

TARGETS = {
    "claude": Path("CLAUDE.md"),
    "codex": Path("AGENTS.md"),
    "opencode": Path("AGENTS.md"),
    "pi": Path(".pi") / "APPEND_SYSTEM.md",
}

ALIASES = {
    "open-code": "opencode",
    "openai-codex": "codex",
}

ENV_SIGNALS = (
    ("claude", ("CLAUDECODE", "CLAUDE_CODE", "CLAUDE_CODE_ENTRYPOINT")),
    ("opencode", ("OPENCODE", "OPENCODE_SESSION")),
    ("codex", ("CODEX_CLI", "CODEX_HOME", "CODEX")),
    ("pi", ("PI_CODING_AGENT", "PI_CODING_AGENT_DIR", "PI_PROFILE")),
)
PROCESS_SIGNALS = ("claude", "opencode", "codex", "pi")


def normalize_agent(value: str) -> str:
    """Return the canonical agent id or raise a useful CLI error."""

    canonical = ALIASES.get(value.strip().lower(), value.strip().lower())
    if canonical not in TARGETS:
        supported = ", ".join(TARGETS)
        raise ValueError(f"unsupported agent {value!r}; choose one of: {supported}")
    return canonical


def running_process_names() -> set[str]:
    """Best-effort process scan used only when --agent is omitted."""

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            names: set[str] = set()
            for line in result.stdout.splitlines():
                if not line.startswith('"'):
                    continue
                name = line.split('","', 1)[0].strip('"').lower()
                names.add(name.removesuffix(".exe"))
            return names

        result = subprocess.run(
            ["ps", "-A", "-o", "comm="],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            Path(line.strip()).name.lower()
            for line in result.stdout.splitlines()
            if line.strip()
        }
    except (OSError, subprocess.SubprocessError):
        return set()


def detect_agent() -> str | None:
    """Detect one supported agent, or return None."""

    for agent, names in ENV_SIGNALS:
        if any(os.environ.get(name) for name in names):
            return agent

    processes = running_process_names()
    for name in PROCESS_SIGNALS:
        if name in processes:
            return name
    return None


def _read_source(source_file: Path) -> bytes:
    source = source_file.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"prompt source not found: {source}")
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"prompt source is empty: {source}")
    return text.encode("utf-8")


def _read_existing(target: Path) -> bytes | None:
    if not target.is_file():
        return None
    return target.read_bytes()


def _print_api_launcher_hint(agent: str, repo_root: Path, source_file: Path) -> None:
    """Explain how to start a new process with the same user prompt."""

    resolved_repo = repo_root.resolve()
    resolved_source = source_file.resolve()
    repo_argument = ""
    if resolved_repo != DEFAULT_REPO_ROOT.resolve():
        repo_argument = f' --repo-root "{resolved_repo}"'
    print("Project-file installation does not retroactively change the current session.")
    print("To pass the same user-supplied prompt to a NEW process, launch:")
    print(
        f"  powershell -ExecutionPolicy Bypass -File {LAUNCHER_PS1}"
        f' --agent {agent} --source "{resolved_source}"{repo_argument} --'
    )
    print(
        f"  bash {LAUNCHER_SH} --agent {agent}"
        f' --source "{resolved_source}"{repo_argument} --'
    )


def install(repo_root: Path, agent: str, source_file: Path, dry_run: bool = False) -> int:
    """Append a user-supplied prompt without overwriting existing content."""

    target = (repo_root / TARGETS[agent]).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"target escapes repository root: {target}") from exc

    source = _read_source(source_file)
    existing = _read_existing(target)

    if existing is not None and source in existing:
        print(f"Already present: {target}")
        _print_api_launcher_hint(agent, repo_root, source_file)
        return 0

    if dry_run:
        mode = "append to existing" if existing is not None else "create"
        print(f"[dry-run] Agent: {agent} -> {target}")
        print(f"[dry-run] Source: {source_file.resolve()}")
        print(f"[dry-run] Would {mode}: {target}")
        return 0

    if existing is None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source)
        print(f"Installed user prompt (created): {target}")
    else:
        separator = b"\n---\n\n" if existing.endswith((b"\n", b"\r")) else b"\n\n---\n\n"
        target.write_bytes(existing + separator + source)
        print(f"Installed user prompt (appended): {target}")

    print("Start a new session for project-file instructions to take effect.")
    _print_api_launcher_hint(agent, repo_root, source_file)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install a user-supplied system prompt for Claude, Codex, OpenCode, or Pi."
    )
    parser.add_argument(
        "--agent",
        help="running agent: claude, codex, opencode, or pi (aliases accepted)",
    )
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
        help="repository root to install into (default: this checkout)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the target and mode without writing",
    )
    args = parser.parse_args(argv)

    try:
        agent = normalize_agent(args.agent) if args.agent else detect_agent()
        if agent is None:
            supported = ", ".join(TARGETS)
            print(
                "ERROR: Could not identify the running agent. "
                f"Run again with --agent ({supported}).",
                file=sys.stderr,
            )
            return 2
        repo_root = args.repo_root.resolve()
        print(f"Agent: {agent} -> {repo_root / TARGETS[agent]}")
        return install(repo_root, agent, args.source, args.dry_run)
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
