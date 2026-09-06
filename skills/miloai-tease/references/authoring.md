# Milo Authoring Guide

Read this guide in full before creative tease authoring, Outline design, or dialogue generation. It combines the core experience model, Outline contract, and gameplay design router. Load detailed gameplay pattern files only for serious candidate designs or the chosen composition.

## Experience model

A Milo tease is an interactive story: narrative, character performance, media, player actions, choices, chance, timers, challenges, and state can all contribute to progression toward intentional endings.

An Outline node is a meaningful part of the experience: a scene, phase, challenge, hub, branch, repeated structure, failure route, or ending. Small variations that do not change the larger route should stay inside one node.

Milo can present narration, dialogue, images, audio, and multiple text beats over persistent media. It can ask the player to choose, enter text, wait, act under time pressure, repeat activities, or respond to persistent prompts. It can branch, randomize, loop, track state, gate content, and persist selected progress when the design requires it.

During Outline work, reason in terms of player experience and capabilities rather than EOS command syntax. Concrete Pages, command payloads, Timer fields, JavaScript APIs, and compiler expansion rules belong to Milo IR or runtime work.

## Outline

`outline.yaml` is the design source. It records work-level intent, meaningful nodes, and permitted cross-node routes. It does not contain executable runtime commands.

### Schema

```yaml
format: milo-outline
title: Example work
brief: |
  A tense interactive story that escalates toward a final challenge.
entry: opening
nodes:
  opening:
    name: Opening
    content: |
      Establish the character, premise, and first meaningful interaction.
    next:
      - to: challenge
        when: The player begins
        priority: main

  challenge:
    name: Challenge
    content: |
      Increase pressure through interaction, feedback, and state changes.
    next:
      - to: ending
        when: The challenge succeeds
        priority: main
      - to: failure
        when: The challenge fails
        priority: fail

  ending:
    name: Ending
    content: Resolve the main route.
    next: []

  failure:
    name: Failure
    content: Resolve failure, recovery, retry, or terminal consequence.
    next: []
```

Top-level fields are closed: unknown fields fail parsing.

| Field | Required | Meaning |
| --- | --- | --- |
| `format` | yes | exactly `milo-outline` |
| `title` | yes | non-empty work title |
| `brief` | no | concise free-text work summary when useful |
| `entry` | yes | first node ID |
| `nodes` | yes | non-empty mapping of node IDs to nodes |

Every node contains exactly:

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | human-readable display name |
| `content` | yes | free-text authoring intent for this node |
| `next` | yes | permitted cross-node exits; `[]` for a terminal node |

Each `next` entry contains:

| Field | Required | Meaning |
| --- | --- | --- |
| `to` | yes | target Outline node ID |
| `when` | no | free-text explanation of when or why the route is used |
| `priority` | no | `main`, `side`, or `fail`; default `main` |

`priority` is authoring metadata. Executable branching conditions belong to Milo IR.

### brief and node content

Use `brief` only when a concise work-level summary adds useful context. It is not a separate stage or deliverable.

`content` has no internal schema. It may naturally combine story intent, dialogue direction, media intent, interaction, pacing, success/failure behavior, and implementation notes useful to later authoring. Do not turn it into another configuration language.

### Node boundaries

Create separate nodes when the distinction matters to the experience graph: major scenes, phases, hubs, branches, repeated structures, failure routes, or endings.

Keep local choices, short loops, and small variations inside a node when they do not materially change the larger route. Split by experience structure, not by Page count or implementation size.

A useful test: if changing a detail would alter node purpose, node boundaries, a cross-node route, a loop, a failure route, or an ending, it belongs in Outline reasoning. Otherwise it can usually wait for Milo IR.

### IDs and routes

Node IDs start with a letter or underscore and may contain letters, digits, underscores, or hyphens, up to 120 characters. Prefer `kebab-case` for authored nodes.

The mapping key is the stable source ID; `name` is only the display name. Renaming an ID requires updating its scene file, entry references, edges, and external Milo IR targets.

An empty `next` marks an intentional Outline-level terminal.

Build requires:

- `entry` and every `next.to` target to exist;
- legal priority values;
- one Milo IR scene per Outline node and one Outline node per Milo IR scene;
- every external `$node` jump to be declared by the current node's `next` list.

Unreachable nodes, duplicate exits, and a graph with no terminal node are warnings. Missing targets and illegal priorities are errors.

Outline owns node identity, purpose, and permitted cross-node routes. Milo IR owns Pages, commands, executable conditions, state changes, media execution, and local control flow.

### Common graph shapes

These are structural guides, not extra schema and not substitutes for gameplay design:

| Shape | Typical use | Typical graph |
| --- | --- | --- |
| Linear phases | mostly ordered escalation | `opening → phase-1 → phase-2 → finale` |
| Chapter/checkpoint | days, acts, missions, saves | `menu → chapter → checkpoint → next-chapter` |
| Hub loop | repeated activity selection | `opening → hub ↔ activity → result → hub → finale` |
| Resource growth | repeated earning/spending and stronger stages | `setup → hub → mission → reward → hub → boss` |
| Random dispatcher | repeated event or board dispatch | `setup → dispatcher ↔ event → ending` |
| Map exploration | meaningful adjacency and collection | `setup → map ↔ area → challenge → finale` |

Choose node boundaries around meaningful changes in the player's loop, state, failure handling, or progression. Use the Gameplay design section below to decide what the player actually does inside those structures.

### Media references

Media intent may be written naturally in node `content` as project-relative authoring context. It does not create runtime media commands. Load `media.md` when selecting, sourcing, grouping, sequencing, generating, or working with detailed media path syntax.

### Tease Graph

Tease Graph edits `outline.yaml`. Visual graph layout is stored separately in `tease-graph-layout.json` and is not part of the Outline schema.

## Writing Guide

Read [`writing-guide-en.md`](writing-guide-en.md) or [`writing-guide-zh.md`](writing-guide-zh.md).

## Gameplay design

This is the entry point for **designing gameplay**, not merely for implementing a mechanic the user has already named.

When a phase, node, encounter, or sequence needs gameplay, start from the intended player experience. Do not begin by asking whether the content is a Maze, Lottery, system, or component. Those are candidate patterns, not top-level design categories.

### Design from the phase purpose

Before selecting a pattern, determine what this phase is supposed to change for the player:

1. **Purpose** — Why does this phase exist in the overall tease? Tutorial, exploration, escalation, recovery, test, discovery, consequence, finale, or something else?
2. **Experience** — What should the player feel here: agency, uncertainty, pressure, restraint, overload, mastery, danger, relief, anticipation?
3. **Player activity** — What should the player actually do repeatedly, not just read?
4. **Agency** — Is success driven mainly by choice, execution, endurance, knowledge, luck, exploration, or accumulated state?
5. **Failure** — Does failure branch, punish, retry, alter later state, offer surrender, or simply end the challenge?
6. **Escalation** — If the phase repeats, what changes each cycle?

A phase does not need a mechanic merely because mechanics exist. Narrative bridges and recovery beats may be intentionally simple.

### Keep references project-agnostic

Gameplay references describe reusable design patterns, not the canon of any one tease or game.

- Do not hard-code project-specific locations, factions, character types, collectibles, endings, lore terms, or named objectives into a pattern's core model.
- Prefer neutral state such as `currentLocation`, `objectiveProgress`, `accessFlags`, `difficulty`, and `contentEnabled` over story-specific variables.
- Examples may demonstrate a mechanic, but the mechanic must still make sense after replacing every example noun with another setting.
- If a design depends on a particular project's world, keep that material in the project Outline/content instead of promoting it into this reference library.

### Example naming convention

Use one consistent naming style in gameplay reference examples:

- **Page, Outline node, Notification, and other authored string IDs:** `kebab-case` (`edge-recovery`, `hud-status`).
- **Milo state IDs:** `camelCase` (`bonusUnlocked`, `voiceEnabled`). Milo state identifiers cannot use hyphens.
- **JavaScript variables and functions:** `camelCase` (`edgeCount`, `handleEdgeEvent`).
- Use uppercase acronyms only as ordinary labels or domain terms, not as a competing identifier style.

This is an authoring convention, not a claim that underscores are invalid in Milo.

### Compose gameplay

Prefer this composition model:

- Choose **one anchor pattern** that defines what the player mainly does in the phase.
- Add **zero to two modifier patterns** only when they materially improve the intended experience.
- Add support/persistence patterns only when the work actually needs them.

Do not stack mechanics just to demonstrate variety. A clear simple game with meaningful escalation is usually stronger than five simultaneous systems.

### Choose patterns by desired experience

| Desired phase experience | Strong candidate patterns | Typical design use |
|---|---|---|
| Forward progress with chance, setbacks, and special spaces | [`roll-and-move-board.md`](gameplay/patterns/roll-and-move-board.md) | Advance along a track by random movement, resolve special positions, and reach a finish condition. |
| Exploration / getting lost / discovery | [`maze.md`](gameplay/patterns/maze.md), [`map-exploration.md`](gameplay/patterns/map-exploration.md) | Navigate locations, find gates, choose routes, revisit places. |
| Knowledge / correctness / streak pressure | [`quiz-challenge.md`](gameplay/patterns/quiz-challenge.md) | Answer objectively checkable questions; let correctness alter score, streak, stakes, or later routes. |
| Deduction / clues / problem solving | [`puzzle-challenge.md`](gameplay/patterns/puzzle-challenge.md) | Gather or inspect information, derive a solution, validate it, and use feedback or hints to progress. |
| Scarcity / planning / tradeoffs | [`resource-economy.md`](gameplay/patterns/resource-economy.md) | Earn a limited resource, choose when to spend or save it, and let those transactions change future options. |
| Finite uncertainty / depletion / card memory | [`deck-draw.md`](gameplay/patterns/deck-draw.md) | Draw from a finite set whose remaining composition changes after each draw. |
| Temptation / escalating voluntary risk | [`push-your-luck.md`](gameplay/patterns/push-your-luck.md) | Repeatedly choose whether to bank current gains or risk them for a better result. |
| Recurring random mode changes / spin suspense | [`wheel-of-fortune.md`](gameplay/patterns/wheel-of-fortune.md) | Repeatedly spin a stable wheel, apply the selected sector as the current rule or mode, and keep looping until the phase ends or switches to a finishing wheel. |
| Uncertainty / anticipation / surprise | [`lottery.md`](gameplay/patterns/lottery.md), [`random-encounters.md`](gameplay/patterns/random-encounters.md), [`deck-draw.md`](gameplay/patterns/deck-draw.md) | Let outcomes or encounters vary; use a deck when previous draws should change what can happen next. |
| Controlled randomness without annoying repeats | [`random-pool-control.md`](gameplay/patterns/random-pool-control.md) | Add no-repeat, cooldown, weighting, or guarantees to another random pattern. |
| Pressure / endurance / urgency | [`timed-challenge.md`](gameplay/patterns/timed-challenge.md), [`race.md`](gameplay/patterns/race.md) | Survive for a duration or hit a target before time runs out. |
| Divided attention / mental overload | [`dual-task-challenge.md`](gameplay/patterns/dual-task-challenge.md) | Keep one action going while counting, observing, remembering, or answering. |
| Restraint / obedience / precision | [`self-control-challenge.md`](gameplay/patterns/self-control-challenge.md) | Maintain silence, balance, posture, speed, or another behavioral rule. |
| Rhythm / changing physical intensity | [`metronome-stroking.md`](gameplay/patterns/metronome-stroking.md) | Build play around cadence, pace, grip, stroke count, or area changes. |
| Repeated build-up and relief | [`edge-hold-loop.md`](gameplay/patterns/edge-hold-loop.md) | Build → edge → hold/stop → recover → repeat. |
| Permission / denial / consequence | [`edge-cum-permission.md`](gameplay/patterns/edge-cum-permission.md) | Apply cross-scene state rules to edge/cum events. |
| Failure that becomes more gameplay | [`retry-loop.md`](gameplay/patterns/retry-loop.md) | Retry with feedback, altered pressure, or a handicap. |
| Pressure while preserving a meaningful way out | [`surrender-option.md`](gameplay/patterns/surrender-option.md) | Keep a persistent authored surrender decision available. |
| Long-form escalation / milestones | [`progression.md`](gameplay/patterns/progression.md) | Track stages, completions, unlocks, and later behavior. |

### Pattern catalog

Every pattern has the same compact **Design profile**. Use those attributes to compare candidates instead of relying on directory categories.

| Pattern | Role | Typical scale | Can lead a phase? |
|---|---|---|---|
| [`roll-and-move-board.md`](gameplay/patterns/roll-and-move-board.md) | Anchor | phase / whole work | Yes |
| [`maze.md`](gameplay/patterns/maze.md) | Anchor | phase / multi-scene | Yes |
| [`map-exploration.md`](gameplay/patterns/map-exploration.md) | Anchor | phase / whole work | Yes |
| [`quiz-challenge.md`](gameplay/patterns/quiz-challenge.md) | Anchor or modifier | scene / phase | Yes |
| [`puzzle-challenge.md`](gameplay/patterns/puzzle-challenge.md) | Anchor or scene | scene / phase | Yes |
| [`resource-economy.md`](gameplay/patterns/resource-economy.md) | Anchor or support | phase / whole work | Yes |
| [`deck-draw.md`](gameplay/patterns/deck-draw.md) | Anchor or modifier | scene / phase | Yes |
| [`push-your-luck.md`](gameplay/patterns/push-your-luck.md) | Anchor or scene | scene / phase | Yes |
| [`wheel-of-fortune.md`](gameplay/patterns/wheel-of-fortune.md) | Anchor or scene | scene / phase | Yes |
| [`lottery.md`](gameplay/patterns/lottery.md) | Anchor or scene | scene / phase | Yes |
| [`random-encounters.md`](gameplay/patterns/random-encounters.md) | Anchor | phase | Yes |
| [`timed-challenge.md`](gameplay/patterns/timed-challenge.md) | Anchor or modifier | scene / phase | Yes |
| [`race.md`](gameplay/patterns/race.md) | Anchor scene | scene / short phase | Yes |
| [`dual-task-challenge.md`](gameplay/patterns/dual-task-challenge.md) | Anchor or modifier | scene / short phase | Yes |
| [`self-control-challenge.md`](gameplay/patterns/self-control-challenge.md) | Anchor or modifier | scene / phase | Yes |
| [`metronome-stroking.md`](gameplay/patterns/metronome-stroking.md) | Anchor or modifier | scene / phase | Yes |
| [`edge-hold-loop.md`](gameplay/patterns/edge-hold-loop.md) | Anchor or modifier | scene / phase | Yes |
| [`random-pool-control.md`](gameplay/patterns/random-pool-control.md) | Modifier | scene / phase | Usually no |
| [`retry-loop.md`](gameplay/patterns/retry-loop.md) | Modifier | scene / phase | Usually no |
| [`surrender-option.md`](gameplay/patterns/surrender-option.md) | Cross-phase modifier | scene / cross-phase | No |
| [`edge-cum-permission.md`](gameplay/patterns/edge-cum-permission.md) | Modifier / cross-phase rule | scene / cross-phase | Usually no |
| [`progression.md`](gameplay/patterns/progression.md) | Support / progression | phase / whole work | Usually no |
| [`settings.md`](gameplay/patterns/settings.md) | Support | whole work | No |
| [`content-gating.md`](gameplay/patterns/content-gating.md) | Support | whole work | No |
| [`unlock-codes.md`](gameplay/patterns/unlock-codes.md) | Support / reward | scene / whole work | No |
| [`save-resume.md`](gameplay/patterns/save-resume.md) | Support / persistence | whole work | No |

### How to recommend gameplay during Outline design

If the user has described the phase but has **not** named a mechanic, do not wait for them to say “Maze”, “Lottery”, or another pattern name.

1. Infer the phase purpose and desired player experience from the current Outline context.
2. Use the table above to identify a small set of plausible anchor patterns.
3. Read the full reference for each candidate you are seriously considering.
4. Propose **2–4 meaningfully different gameplay designs**, each described in player-facing terms: what the player repeatedly does, how it escalates, and how success/failure changes the scene.
5. Recommend or draft the best-fitting option when the user has delegated the decision. Do not dump the entire pattern catalog.

If the user already named a pattern, read that pattern directly and any modifiers that materially interact with it.

### Examples of composition

- **Board progression phase:** `roll-and-move-board.md` as anchor + `random-encounters.md` for ordinary spaces + `progression.md` when later sections increase difficulty; special spaces may offer optional challenges that reward advancement or impose setbacks.
- **Exploration phase:** `maze.md` as anchor + `random-encounters.md` for room variability + `progression.md` only if discoveries change later routes.
- **Knowledge-risk phase:** `quiz-challenge.md` as anchor + `push-your-luck.md` when the player can bank a streak/reward or risk it on another question.
- **Card-risk phase:** `deck-draw.md` as anchor + `push-your-luck.md` when the changing remaining deck informs whether the player should stop or draw again.
- **Wheel phase:** `wheel-of-fortune.md` as anchor + `timed-challenge.md` when the wheel repeatedly changes the current mode for a bounded phase; add `random-pool-control.md` only when repeat suppression, dynamic weighting, cooldowns, or guarantees are deliberate requirements.
- **Resource-planning phase:** `resource-economy.md` as anchor when repeated earning/spending decisions drive play; pair it with `progression.md` only when purchases or milestones alter later rules.
- **Divided-attention phase:** `dual-task-challenge.md` as anchor + `metronome-stroking.md` + a short `retry-loop.md` for mistakes.
- **Performance phase:** `race.md` or `self-control-challenge.md` as anchor + `timed-challenge.md`; add retry only if repeating the task stays interesting.
- **Denial/endurance phase:** `edge-hold-loop.md` as anchor + `edge-cum-permission.md` + optional `surrender-option.md`.
- **Unpredictable encounter phase:** `random-encounters.md` as anchor + `random-pool-control.md` when no-repeat or guarantees matter.

### Loading rule

Read this index first whenever gameplay materially affects design or implementation. Then read the **smallest set of pattern files that covers the serious candidate designs or the chosen composition**. The index is a design router, not sufficient implementation guidance by itself.
