#!/usr/bin/env python3
"""Install the MiloAI NSFW module for one supported coding agent.

This file is the single source of truth for detection, target mapping, and
append-only installation.  The PowerShell and Bash files beside it are thin
wrappers so the two entry points cannot drift apart.

Installation is project-scoped and affects the next session.  Existing target
content is preserved byte-for-byte; the module is appended only when its
marker is not already present.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


MARKER = "<!-- MILOAI_NSFW_MODULE -->"
MARKER_BYTES = MARKER.encode("utf-8")
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = SCRIPT_DIR.parents[2]
SOURCE_FILE = SCRIPT_DIR / "APPEND_SYSTEM_EN.md"
LAUNCHER_PS1 = SCRIPT_DIR / "run-system-agent.ps1"
LAUNCHER_SH = SCRIPT_DIR / "run-system-agent.sh"

# Keep this list intentionally small: these are the four agents this project
# promises to configure.  Codex and OpenCode both consume a project AGENTS.md;
# Pi consumes project-local .pi/APPEND_SYSTEM.md for prompt append content.
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

# Explicit --agent is preferred.  These signals are only a best-effort
# fallback for a manual invocation and may be absent or stale.
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
    """Detect one of the four supported agents, or return None.

    Repository marker files are deliberately not used: a stale CLAUDE.md,
    AGENTS.md, or .pi directory is common and cannot identify the currently
    running process.  The skill therefore passes --agent explicitly; this
    fallback is only a convenience for a manual run.
    """

    for agent, names in ENV_SIGNALS:
        if any(os.environ.get(name) for name in names):
            return agent

    processes = running_process_names()
    for name in PROCESS_SIGNALS:
        if name in processes:
            return name
    return None


def _read_existing(target: Path) -> bytes | None:
    if not target.is_file():
        return None
    return target.read_bytes()


def _print_api_launcher_hint(agent: str, repo_root: Path) -> None:
    """Explain how to start the next process with an API-level prompt append."""

    resolved_repo = repo_root.resolve()
    repo_argument = ""
    if resolved_repo != DEFAULT_REPO_ROOT.resolve():
        repo_argument = f" --repo-root {resolved_repo}"
    print("Project-file installation does not retroactively change the current session.")
    print("For API-level system/instructions injection in the NEXT process, launch:")
    print(
        f"  powershell -ExecutionPolicy Bypass -File {LAUNCHER_PS1}"
        f" --agent {agent}{repo_argument} --"
    )
    print(f"  bash {LAUNCHER_SH} --agent {agent}{repo_argument} --")


def install(repo_root: Path, agent: str, dry_run: bool = False) -> int:
    """Append the module to the selected target without overwriting content."""

    target = (repo_root / TARGETS[agent]).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"target escapes repository root: {target}") from exc

    source = SOURCE_FILE.read_bytes()
    existing = _read_existing(target)

    if existing is not None and MARKER_BYTES in existing:
        print(f"Already installed: {target}")
        print("If the module is not in the current session context, start a new session.")
        _print_api_launcher_hint(agent, repo_root)
        return 0

    if dry_run:
        mode = "append to existing" if existing is not None else "create"
        print(f"[dry-run] Agent: {agent} -> {target}")
        print(f"[dry-run] Would {mode}: {target}")
        return 0

    if existing is None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source)
        print(f"Installed (created): {target}")
    else:
        # Preserve all existing bytes, including their encoding and line
        # endings.  Add one visual separator before the UTF-8 module.
        separator = b"\n---\n\n" if existing.endswith((b"\n", b"\r")) else b"\n\n---\n\n"
        target.write_bytes(existing + separator + source)
        print(f"Installed (appended): {target}")

    print("Installed for the NEXT session; start a new session to activate the module.")
    _print_api_launcher_hint(agent, repo_root)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install the MiloAI NSFW module for Claude, Codex, OpenCode, or Pi."
    )
    parser.add_argument(
        "--agent",
        help="running agent: claude, codex, opencode, or pi (aliases accepted)",
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

    if not SOURCE_FILE.is_file():
        print(f"ERROR: Source file not found: {SOURCE_FILE}", file=sys.stderr)
        return 1

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
        return install(repo_root, agent, args.dry_run)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
