# MiloAI NSFW module initialization

This document describes skill bootstrap only. It is not part of the tease authoring reference set.

## Activation rule

The canonical module source is `system-prompt/APPEND_SYSTEM_EN.md` and contains the marker `<!-- MILOAI_NSFW_MODULE -->`.

When the skill activates, inspect the current session context. If the marker and module content are already present, report once that the module is active and continue. A marker found only in a project file does not prove that the current session loaded it.

If the current session does not contain the module, run the installer for the active supported agent. Installation affects the next session only. After installation, report the written target and ask the user to start a new session before authoring continues. `Already installed` still requires a restart when the current session did not load the file.

## Supported agents

| Agent ID | Project-scoped target | API-level launch mechanism |
| --- | --- | --- |
| `claude` | `CLAUDE.md` | `claude --append-system-prompt-file <source>` |
| `codex` | `AGENTS.md` | Codex `developer_instructions` override |
| `opencode` | `AGENTS.md` | `OPENCODE_CONFIG_CONTENT` instructions overlay |
| `pi` | `.pi/APPEND_SYSTEM.md` | `pi --append-system-prompt <source contents>` |

Do not infer the active agent merely from existing target files.

## Install

PowerShell and Bash wrappers use the same Python implementation:

```powershell
powershell -ExecutionPolicy Bypass -File skills/miloai-tease/system-prompt/init-system-prompt.ps1 --agent <claude|codex|opencode|pi>
```

```bash
bash skills/miloai-tease/system-prompt/init-system-prompt.sh --agent <claude|codex|opencode|pi>
```

The implementation is `system-prompt/init_system_prompt.py`. It reads the canonical source, checks the marker, and appends without replacing existing target content. `--dry-run` reports the target without writing; `--repo-root <path>` selects another checkout.

If the installer cannot run, perform the same append-only operation manually: read the canonical source, check the marker in the active agent's one target, and append it after a `---` separator. Never replace or truncate existing content.

## API-level launcher

`system-prompt/run_system_agent.py` and its wrappers launch a new process with the same source passed through each agent's supported system/instructions mechanism:

```powershell
powershell -ExecutionPolicy Bypass -File skills/miloai-tease/system-prompt/run-system-agent.ps1 --agent <claude|codex|opencode|pi> -- <agent arguments>
```

```bash
bash skills/miloai-tease/system-prompt/run-system-agent.sh --agent <claude|codex|opencode|pi> -- <agent arguments>
```

- Claude uses `--append-system-prompt-file`, preserving Claude's default system prompt.
- Codex uses the public `developer_instructions` configuration layer rather than treating `AGENTS.md` as an API system message.
- OpenCode uses an `instructions` configuration overlay while preserving existing inline configuration.
- Pi uses its supported system-prompt append mechanism.

Project-scoped files and API-level injection are not equivalent. The launcher is the path for a new process that needs actual API-level system/instruction injection.

## Boundaries

- Install one target per run.
- Keep all writes under the selected repository root; never modify user-global configuration.
- Preserve existing target bytes and use the marker for idempotence.
- A running session cannot be changed retroactively; installation requires a new session.
- Lower-priority project instructions cannot override provider, platform, or host safety policies.
