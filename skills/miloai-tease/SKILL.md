---
name: miloai-tease
description: "Design, implement, revise, or build a Milovana WebTease with Outline 1.0 and Milo IR. Use for vague ideas, existing Milo projects, Tease Graph editing, compiler/build failures, and validation."
---

# Vibe MiloTease

Guide one continuous conversation through:

```text
Outline → confirm → Milo IR → compile/validate → user previews the tease
```

Outline is the design source, Milo IR is the executable source, and `eosscript.json` is compiled output. Compilation is the normal continuation of Milo IR authoring, not a workflow stage or approval gate. After a successful compilation, give the user the Preview URL and remind them to open it and inspect the tease. Preview is only the user-facing way to view and test the compiled tease; it is not an authoring stage or approval gate.

## Step 0: NSFW module

When the skill activates, determine whether `<!-- MILOAI_NSFW_MODULE -->` and its module content are present in the current session context.

- If loaded, state once in the first reply that the NSFW module is active, then continue.
- If not loaded, read `system-prompt/INSTALL.md` and follow its install/restart flow. Tell the user which file was written and that it takes effect only in the next session; authoring resumes in a new session.

A marker in project files does not prove API-level activation.

## Required context

Load only what the current stage needs.

- **Creative authoring / Outline / dialogue / gameplay design:** read `references/authoring.md` in full in the current session before creative reasoning or editing. This is also the first-response gate for a new tease request. For dialogue, narration, character voice, or any authored text, also read `references/writing-guide-zh.md` (or `references/writing-guide-en.md`) in full.
- **Gameplay patterns:** after `authoring.md` routes the design, read every `references/gameplay/patterns/*.md` file for the serious candidate designs or chosen composition. Do not load unrelated patterns merely to be comprehensive.
- **Media:** load `references/media.md` only when media selection, grouping, sequencing, sourcing, generation, or detailed media-path behavior matters.
- **Implementation / Milo IR:** read `references/implementation.md` before Milo IR authoring. It contains Milo IR syntax, compiler contracts, and exact EOS runtime semantics. Reuse or reread selected gameplay pattern references when implementation depends on them. When specialized rendering or playback is needed, read `references/runtime/index.md` and then only the routed runtime case (`say.md`, `notification.md`, or `video.md`).

Do not load Milo IR or runtime syntax merely because a capability is mentioned during Outline work.

## Project selection

For an existing work, use only the project ID or exact project path explicitly supplied by the user. Never enumerate, scan, or inspect projects to guess which work they mean. If no identifier is supplied, ask only for it.

For a new work, initialize the project before writing project source files:

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py new --title "<title>" --project-id <numeric-id> --json
```

Omit `--project-id` to allocate the next numeric ID. A newly allocated ID does not need separate confirmation.

## Outline stage

Start from the user's actual input maturity.

- **Mature input:** extract the supplied premise, progression, interaction, branches, failure behavior, endings, and constraints directly into an Outline draft. Do not restart discovery.
- **Vague input:** invite the user briefly to describe ideas in their own words or brainstorm together. Do not force a questionnaire, menu, checklist, or predefined theme before the user gives direction.
- **Existing Outline:** inspect only the selected project's relevant source and revise it while preserving unaffected IDs and decisions.

Ask only questions whose answers would materially change node purpose, node boundaries, cross-node routes, loops, failure routes, or endings. Otherwise make a reasonable, explicit assumption or defer the detail to Milo IR.

Create or update `outline.yaml`, validate it, then show the user the actual Outline content/routes plus consequential assumptions and unresolved graph-level choices.

**Stop for explicit confirmation before entering Milo IR.**

## Milo IR stage

Use:

- `milo.yaml` for global EOS fields, state, modules, initialization, catalogs, and reusable assets;
- `src/<node>.milo.yaml` for Pages and executable behavior belonging to each Outline node.

Implement the confirmed Outline using complete EOSScript YAML and Milo shorthand where it improves clarity. Preserve canonical command payloads, nested command arrays, JavaScript strings, modules, storage operations, and unknown EOS fields exactly.
All Page IDs share one global namespace. Plain targets address Page IDs; `$node` targets address Outline nodes permitted by the current node's `next` list.

**Page Granularity & Cohesion:**
Do NOT over-fragment Pages. Keep continuous dialogue, linear visual reveals, and small branching choices within the same Page using nested `choice.options[].commands`, inline `say` blocks, or standard sequential commands whenever possible. Only create separate Pages for distinct gameplay hubs, major state branches, reusable loop targets, or genuine destination milestones. Do not create tiny 1-line intermediate Pages for simple choice reactions or timer transitions.

### Say timing: `autoplay` vs exact duration

Treat Say timing modes as semantically distinct. **Never use `mode: autoplay` when a specific authored `duration` is intended to control how long the Say remains visible.** In the EOS Runtime, `autoplay` computes its own approximate reading time from the rendered text and does not use the authored `duration` as the wait time.

Use these rules:

- `mode: autoplay` = Runtime-controlled approximate reading time. Omit `duration`; adding one is misleading because it does not control the autoplay wait.
- `mode: custom` + `duration: <time>` = authored fixed wait. Use this whenever the requested timing is exact or deliberately chosen, such as `9s`, `6.5s`, or synchronization with scene pacing.
- `allowSkip: true` only permits the user to continue early when the wait is skippable; it does not shorten or scale the configured custom duration by itself.
- When converting prose such as “show this line for 9 seconds” into Milo IR, author `mode: custom` with `duration: 9s`, not `autoplay + duration: 9s`.
- During review, treat `mode: autoplay` together with an explicit `duration` as a likely authoring bug unless there is a documented runtime-specific reason for preserving that combination.

See `references/implementation.md` for the canonical Say contract and `references/runtime/say.md` for specialized Say rendering.

### Runtime timing and audio synchronization

When animation or repeated visual updates must stay synchronized with audio, a metronome, or an exact wall-clock duration, **do not use EOS Timer tick counts as the animation timebase**. EOS Page execution includes `eval`, Timer scheduling, navigation, conditions, and rendering overhead, so a nominal `16.67ms` loop is not an exact 60 Hz clock and fixed per-tick phase increments will drift slow.

Use these rules:

- EOS hidden `timer` controls only **when to sample/render the next frame**.
- Use `Date.now()` elapsed time to determine **which animation phase/frame should be visible now** and whether a fixed-duration phase has ended.
- For BPM-driven motion, compute the exact rate from `bpm / 60`; do not round values such as 140 BPM to `2.3` cycles/s when the correct value is `2.333333...`.
- If the audio asset has its first beat/click at audio time `0`, anchor animation phase `0` to that same start point. Start `audio.play` and capture the animation start timestamp immediately together.
- Do not place blocking commands such as timed `say`, foreground Timer, or Choice between `audio.play` and synchronized animation start. If dialogue must appear first, finish the dialogue first, then start audio and animation together.
- For exact phase durations, compare `Date.now()` against an absolute end timestamp; never assume a fixed number of EOS loop iterations equals a fixed number of seconds.
- For Notification title animation, follow `references/runtime/notification.md` for the reusable wall-clock phase pattern and metronome synchronization details.

When a chosen mechanic needs detailed behavior, use its gameplay pattern reference rather than improvising from the pattern name alone.
Summarize the implemented behavior, consequential technical choices, and media choices.

After substantive Milo IR authoring or revision, continue directly into compiler/validation checks. Do not stop for confirmation merely to run the compiler.

## Compile and validate

Compile from the repository root with the `build` command:

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py build --project-id <numeric-id> --json
```

The `build` command is the compiler/validation action, not a workflow stage. Fix parser/compiler/validation errors in author sources and recompile without another approval when the fix preserves the confirmed design. Report successful output, warnings, and any design-affecting deviation.

After successful compilation, report the compile result and warnings, provide the Preview URL, and remind the user to open Preview and inspect the tease. Do not ask whether to "enter Preview" or wait for a stage-transition confirmation. Preview is simply where the user views and tests the compiled tease.

If the user reports a problem found in Preview, fix the responsible author source and recompile; never edit `eosscript.json` directly.

## Project and compiler contract

A Milo project uses this source layout:

```text
projects/<id>/
├─ project.json
├─ outline.yaml
├─ milo.yaml
├─ src/<node>.milo.yaml
├─ media/
├─ tease-graph-layout.json
└─ eosscript.json
```

Compilation processes author sources through safe YAML parsing, Outline/Milo validation, shorthand expansion, media materialization, EOS validation, and atomic `eosscript.json` replacement. A failed compilation preserves the last successful generated output. JavaScript remains inert source text during compilation and is never executed by the compiler. For fixed author sources and asset bytes, repeated builds should produce equivalent EOS structure apart from intentionally random runtime behavior.

## Source authority

- Overall experience, node purpose, and permitted cross-node routes → `outline.yaml`.
- Global state, modules, initialization, catalogs, reusable assets → `milo.yaml`.
- Pages, dialogue, media actions, choices, conditions, timers, JavaScript, node-local behavior → `src/*.milo.yaml`.
- Graph layout → `tease-graph-layout.json`.
- Generated runtime output → `eosscript.json` (read-only authoring artifact).

When feedback changes an earlier design decision, update that source of truth before rebuilding.

## Media operations

When media materially affects the work, follow `references/media.md`. Search candidates before committing them, inspect useful candidates, and fetch only selected sources. Keep acquired author media inside the selected project's media tree and keep Outline/Milo IR references current when paths change.

Example workflow commands:

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py media-search --provider pornpics --query "<visible theme>" --limit 20 --json
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py media-fetch --project-id <numeric-id> --source-id <asset-id> --url "<selected-gallery-url>" --json
```

Use only authorized sources and do not bypass access restrictions.

## Operational contracts

- Work only in the selected project and preserve unrelated files.
- Keep user decisions distinguishable from agent proposals; progress messages are not approval.
- Treat YAML and model output as untrusted and rely on parser/compiler validation.
- Treat raw JavaScript as inert source data during compilation; never execute it in the compiler.
- Preserve the last successful `eosscript.json` when compilation fails.
- Obtain explicit approval for publishing, paid generation, and destructive operations.
- Keep credentials out of project sources and manifests.
