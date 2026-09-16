# User-supplied system prompt helpers

This project does **not** provide jailbreak, safety-bypass, "unrestricted", or other bypass prompts. If you choose to use a custom system prompt, you must create and maintain it yourself and pass it explicitly with `--source`.

The helpers in this directory only transport a user-supplied UTF-8 text file to a supported agent. They do not contain a default prompt and do not automatically activate any prompt.

## Supported agents

| Agent ID | Project-scoped target | API-level launch mechanism |
| --- | --- | --- |
| `claude` | `CLAUDE.md` | `claude --append-system-prompt-file <source>` |
| `codex` | `AGENTS.md` | Codex `developer_instructions` override |
| `opencode` | `AGENTS.md` | `OPENCODE_CONFIG_CONTENT` instructions overlay |
| `pi` | `.pi/APPEND_SYSTEM.md` | `pi --append-system-prompt <source contents>` |

Do not infer the active agent merely from existing target files.

## Install a user-supplied prompt into project instructions

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File skills/miloai-tease/system-prompt/init-system-prompt.ps1 --agent <claude|codex|opencode|pi> --source "D:\path\to\my-prompt.md"
```

Bash:

```bash
bash skills/miloai-tease/system-prompt/init-system-prompt.sh --agent <claude|codex|opencode|pi> --source /path/to/my-prompt.md
```

The implementation is `system-prompt/init_system_prompt.py`. `--source` is required. The installer appends the exact user-provided prompt without replacing existing target content. If the same prompt bytes are already present, it does not append them again. `--dry-run` reports the target without writing; `--repo-root <path>` selects another checkout.

Project-file installation affects future agent sessions; it does not retroactively alter a running session.

## Launch a new process with a user-supplied prompt

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File skills/miloai-tease/system-prompt/run-system-agent.ps1 --agent <claude|codex|opencode|pi> --source "D:\path\to\my-prompt.md" -- <agent arguments>
```

Bash:

```bash
bash skills/miloai-tease/system-prompt/run-system-agent.sh --agent <claude|codex|opencode|pi> --source /path/to/my-prompt.md -- <agent arguments>
```

- Claude uses `--append-system-prompt-file`, preserving Claude's default system prompt.
- Codex uses the public `developer_instructions` configuration layer.
- OpenCode uses an `instructions` configuration overlay while preserving existing inline configuration.
- Pi uses its supported system-prompt append mechanism.

## Boundaries

- No default or bundled bypass prompt is provided by this project.
- `--source` must point to a non-empty UTF-8 text file supplied by the user.
- Install one target per run.
- Keep project-file writes under the selected repository root; never modify user-global configuration.
- Existing target bytes are preserved; the supplied prompt is appended only when it is not already present.
- A running session cannot be changed retroactively; project-file installation requires a new session.
- User-supplied prompts remain subject to the provider, platform, host, and model policies that apply to the selected agent.
- Users must ensure their use complies with all laws and regulations applicable in their jurisdiction and actual use context, as well as relevant platform rules and third-party terms, and they assume all risks, responsibilities, and consequences arising from their prompts, content, account actions, publications, and third-party materials.
- The project authors and contributors do not participate in or control users' specific use, and making these helpers available does not constitute endorsement, authorization, or warranty of any user conduct, prompt, content, or purpose. The project authors and contributors assume no responsibility or liability for any loss, claim, penalty, dispute, legal liability, or other direct or indirect consequence arising from such use.
