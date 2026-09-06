# Milo Implementation

Milo IR is the editable executable source for a Milo project. It is YAML that can express complete EOSScript structures plus a small set of Milo shorthand forms.

Use this reference during Milo IR authoring. It combines Milo IR syntax, compiler behavior, and exact EOS runtime semantics so implementation does not depend on a second general runtime document. The creative design and gameplay router live in `authoring.md`; load selected `gameplay/patterns/*.md` references for chosen mechanics and `media.md` when media choices materially affect implementation.

## Files

Global runtime declarations live in `milo.yaml`:

```yaml
format: milo-runtime

state:
  score: 0
  playerName: null

assets:
  opening:
    folder: media/sources/opening
    pick: sequence
    type: image

modules:
  audio: {}

init: |
  var runtimeReady = true;
```

Each Outline node has one scene file in `src/<node>.milo.yaml`:

```yaml
format: milo-ir
scene: opening
entry: intro

pages:
  intro:
    - say: The story begins.
    - goto: decision

  decision:
    - choice:
        Continue: $challenge
        Leave: $ending
```

`format` is optional, but when present it must be `milo-runtime` in `milo.yaml` or `milo-ir` in a scene file.

## Source responsibilities

| Source | Owns |
| --- | --- |
| `milo.yaml` | EOS top-level data, Milo state, modules, initialization, catalogs, reusable assets |
| `src/*.milo.yaml` | Pages and executable command trees for one Outline node |
| `outline.yaml` | node identity and permitted cross-node routes |
| `eosscript.json` | generated output; never author it directly |

Unknown EOS top-level fields in `milo.yaml` are preserved. Raw EOS fields that collide with Milo metadata names `format`, `state`, `assets`, or `eos` go under `milo.yaml.eos`.

## State

`state` maps IDs to scalar initial values: strings, numbers, booleans, or `null`. Lists and mappings are not allowed.

State IDs begin with a letter or underscore and then use letters, digits, or underscores. For authored Milo state, prefer `camelCase` names such as `playerName` and `bonusUnlocked`; avoid snake_case in new examples.

Compact `if`, `set`, and scalar `prompt` reference declared Milo state. Canonical EOS JavaScript uses native runtime variables and is not automatically synchronized with Milo state.

## Assets

An asset may be a direct path:

```yaml
assets:
  opening: media/sources/opening
  heartbeat: media/sources/audio/heartbeat.mp3
```

Or a long form with exactly one source:

```yaml
assets:
  opening:
    folder: media/sources/opening
    pick: sequence
    recursive: true
    include: ["*.jpg", "*.png", "*.webp"]
    exclude: ["draft-*"]
    type: image
```

Sources are:

- `folder` — scan a folder for supported media;
- `file` — one image or audio file;
- `locator` — an authored EOS locator.

Optional fields are `pick` (`sequence`, `random`, `first`), `recursive`, `include`, `exclude`, and `type` (`image` or `audio`).

Relative paths resolve from the project directory and may not escape it. Explicit absolute paths are treated as external read-only sources. Build materializes source bytes into project output using stable content-derived filenames.

Supported authored image formats are JPG/JPEG, PNG, WebP, BMP, and GIF. The compiler can catalog MP3, WAV, OGG, M4A, AAC, and FLAC sources, but the bundled EOS `audio.play` resolver requests `audio/mpeg`; use MP3 for runtime playback and preload compatibility.

GIF sources materialize from their first frame. Image locators commonly use `file:` or `gallery:`; audio normally uses `file:`. Raw EOS locators are preserved even when Milo does not recognize their scheme.

Media shorthand resolves, in order: explicit locator, asset alias, existing catalog name, filesystem path, then unique indexed filename. Ambiguous names fail Build.

## Scene and Page contract

Each scene file contains:

| Field | Required | Meaning |
| --- | --- | --- |
| `format` | no | `milo-ir` when present |
| `scene` | yes | Outline node ID implemented by the file |
| `entry` | yes | entry Page ID for the scene |
| `pages` | yes | non-empty mapping of Page IDs to command lists |

All scenes share one global Page namespace. Duplicate Page IDs fail Build.

**Page Granularity Principle:**
- **Avoid Over‑Fragmenting Pages**: A continuous scene dialogue, linear visual performance or simple branching options should be kept within the same Page as much as possible. Use the inline‑command array of `choice.options[].commands` or sequential `say`/`image`/`timer` for smooth presentation, instead of creating a new fragmented Page with only 1‑2 lines of instructions for every line of dialogue or each small branch.
- **When to Split a Page**: An independent Page shall only be created when encountering a core‑state Hub (such as map fork‑selection, level roulette lobby), reusable jump targets (such as loop anchor, failure/success settlement point), or cross‑node jump boundaries.
- Maintain complete logic and stage continuity for each Page. Avoid frequent meaningless `goto` statements that interrupt the audio lifecycle or cause UI flicker.



Page IDs are non-empty strings and are preserved as authored. They are not subject to the Outline/scene/asset ID regex; underscores are valid. For readable static targets, prefer stable `kebab-case` names such as `edge-recovery` and `chapter-hub`. Underscores remain valid but are not the preferred authoring style.
Each command is a single-key mapping. Canonical EOS command payloads are preserved as authored, including nested command arrays, JavaScript strings, module payloads, future fields, and unknown commands. Unknown commands remain valid source and produce warnings rather than being rewritten into a smaller Milo schema.

The commonly authored canonical surface includes:

| Command | Core canonical payload |
| --- | --- |
| `image` | `locator` |
| `say` | `label` plus presentation fields |
| `goto` | `target` |
| `timer` | `duration`, `style`, `isAsync`, `commands` |
| `choice` | `options` with targets or nested commands |
| `prompt` | `variable` |
| `eval` | `script` |
| `if` | `condition`, `commands`, optional `elseCommands` |
| `enable` / `disable` | `target` |
| `notification.create` / `notification.remove` | notification payload |
| `audio.play` / `audio.stop` | audio payload |
| `storage`, `noop`, unknown commands | opaque EOS/module payload preserved |

## Targets

Milo distinguishes local/global Page targets from Outline-node targets:

```yaml
- goto: next-round   # global Page ID
- goto: $ending      # entry Page of another Outline node
```

A `$node` target is legal only when the current Outline node declares that node in `next`.

Canonical EOS targets are preserved exactly:

```yaml
- goto:
    target: next-round
```

## Canonical EOS and Milo shorthand

Mappings using canonical EOS payloads always take precedence over shorthand. Milo shorthand exists for common authoring tasks; it does not limit EOS functionality.

### Say

```yaml
- say: Plain narration or dialogue
```

Canonical form:

```yaml
- say:
    label: I was waiting for you.
    mode: autoplay
    align: right
    allowSkip: true
```

Use the EOS-native `align` field for Say alignment. Valid values are:

```yaml
align: left
align: center
align: right
```

`align` controls the Say bubble/presentation alignment. Do **not** try to replace it with rich-text HTML such as `<p style="text-align:right">...</p>`; HTML `text-align` is not the command-level Say alignment mechanism and should not be relied on to position a Say bubble. If different beats need different alignment, author them as separate Say commands with their own `align` values.

Canonical Say may use EOS rich-text HTML and inline `<eval>expression</eval>` inside `label`. Supported inline styling can be used deliberately to create a visual language for different kinds of text, for example:

- character dialogue — a character-specific color and, when useful, left/right Say alignment;
- thoughts or internal voice — a quieter color, smaller size, or emphasis;
- narration / background context — neutral styling, often smaller or centered when appropriate;
- actions, rules, warnings, or important instructions — stronger contrast, larger size, or bold emphasis.

Example:

```yaml
- say:
    label: '<span style="color:#e9a8c6;font-size:1.05em">You came back.</span>'
    align: right

- say:
    label: '<span style="color:#a8a8a8;font-size:0.9em"><em>I should probably leave...</em></span>'
    align: center

- say:
    label: '<span style="color:#ffd36a;font-size:1.1em"><strong>Keep your hands where they are.</strong></span>'
    align: left
```

Use color, size, emphasis, and alignment consistently enough that the player can infer the distinction, but do not style every line differently. Presentation timing, alignment, and skip behavior remain EOS Say semantics.

### Image

```yaml
- image: opening/next
- image: opening/random
- image: opening/specific-file.png
```

The first component may be an asset ID. A direct EOS locator, catalog name, path, or unique indexed filename may also be used. Canonical form uses `image.locator`.

For video-like playback without modifying the EOS runtime, including frame extraction, gallery packaging, hidden-Timer pacing, page chunking, and optional synchronized audio, read `runtime/video.md`.

### Audio

```yaml
- audio: heartbeat
- audio:
    asset: heartbeat
    action: play
    volume: 0.6
    loops: 1
- audio:
    asset: heartbeat
    action: stop
```

Audio shorthand resolves Milo assets and enables the audio module automatically. Exact playback semantics are defined in the Runtime semantics section below.

For shorthand, `action` is `play` or `stop`, `volume` is from 0 to 1, and `loops` is a non-negative integer.

### Preload

Use `preload` when a tease should explicitly cache its generated media catalog before continuing:

```yaml
- preload:
    to: main-menu
    message: Click to start preloading. Estimated load: {size}.
    button: Start preload
```

`preload` automatically enumerates all generated gallery images and catalog audio files, deduplicates them by content hash when available, calculates the estimated transfer size, enables Notification/Audio modules as needed, and generates internal hidden preload batches. Authors do not need to write hundreds of `image` or `audio.play` commands by hand.

The action renders a Say followed by a button. Media loading starts only after that button is pressed. Each hidden batch is fully preloaded by EOS before its Page commands run; the first command then advances the Notification using completed resource count and cumulative bytes, and navigates to the next hidden batch before any image/audio preload command can visibly execute. This avoids browser-only `setInterval`/Resource Timing APIs, has no preload timeout, and keeps preload images/audio invisible and silent.

Supported placeholders in `message` are `{size}`, `{bytes}`, `{images}`, `{audio}`, and `{total}`. The progress Notification template additionally supports `{percent}`, `{loaded}`, and `{bar}`:

```yaml
- preload:
    to: main-menu
    message: Click to start preloading. Estimated load: {size}.
    button: Start preload
    notification: Loading {percent}%  {bar}
    bar_width: 10
```

`scope` currently defaults to and only supports `all`. The automatic catalog covers enumerated gallery images and runtime-compatible `audio/mpeg` files. Non-MP3 audio is skipped because the bundled EOS audio module resolves preload/playback locators as `audio/mpeg`; convert such sources to MP3 when they must play or preload. Opaque external/direct locators whose contents are not present in the EOS catalog cannot be globally enumerated.

### Wait and Timer shorthand

```yaml
- wait: 30s
- wait: 1m30s
- timer: 250ms
```

Scalar `timer` and `wait` are the same Milo shorthand. A Timer mapping is canonical EOS and is preserved as written. Exact Timer behavior is defined in the Runtime semantics section below.

A bare positive number means seconds. Fixed shorthand strings may combine `h`, `m`, `s`, and `ms` units in that order, including decimals.

### Goto

```yaml
- goto: next-round
- goto: $ending
- goto: challenge-*
```

Wildcard targets are preserved for EOS runtime selection. Exact wildcard and Page availability behavior is defined in the Runtime semantics section below.

### Choice

Compact form:

```yaml
- choice:
    Continue: challenge
    Give up: $failure
```

List shorthand may add fields such as button color and nested commands:

```yaml
- choice:
    - label: Continue
      to: challenge
      color: primary
```

Canonical `choice: {options: [...]}` is preserved unchanged.

### Enable and disable

```yaml
- disable: challenge-easy
- enable: challenge-*
```

Canonical mappings use a `target` field. Runtime meaning is defined in the Runtime semantics section below.

### If

Compact form:

```yaml
- if:
    score >= 3 and permission: success
    score >= 1: retry
    else: failure
```

Compact conditions may use declared state IDs, scalar literals, comparisons, `and`, `or`, `not`, and parentheses. Canonical EOS `if` mappings may contain arbitrary EOS condition strings and nested commands and are preserved unchanged.

Compact precedence is parentheses, `not`, `and`, then `or`.

### Random

```yaml
- random:
    common: 80
    rare: 20
```

Weights are positive relative numbers and do not need to total 100.

### Set

```yaml
- set: score += 1
- set: permission = true
```

Long form:

```yaml
- set:
    variable: score
    op: +=
    value: 1
```

Supported operators are `=`, `+=`, `-=`, `*=`, and `/=`. The right side is one scalar literal or one declared state ID. Build expands shorthand into deterministic EOS JavaScript.

### Prompt

```yaml
- prompt: playerName
```

Scalar Prompt references declared Milo state. A Prompt mapping is canonical EOS and uses native runtime variable behavior. Runtime input behavior is defined in the Runtime semantics section below.

### Notification

```yaml
- notification: Time is almost over.
- notification:
    id: warning
    title: Time is almost over.
    button: Continue
    to: retry
- notification:
    remove: warning
```

Notification shorthand enables the notification module automatically. Canonical `notification.create` and `notification.remove` mappings are preserved unchanged.

`button` and `button_label` are accepted shorthand labels for the notification button.

### End

```yaml
- end: true
```

An empty mapping is also accepted.

`end` terminates the tease and returns control to the EOS ending/rating flow.

## Raw EOS and JavaScript

Canonical EOS can be authored directly:

```yaml
- eval:
    script: gameState.save({score: score});

- timer:
    duration: 10
    isAsync: true
    commands:
      - goto:
          target: timeout
```

Build stores JavaScript strings without executing or rewriting them. Runtime APIs and execution semantics are defined in the Runtime semantics section below.

## Compiler contract

Build performs, in order:

```text
safe YAML loading
→ Outline and Page ownership validation
→ shorthand expansion and media materialization
→ raw EOS preservation
→ EOS reference/module/reachability validation
→ atomic eosscript.json replacement
```

Build validates known Page, node, asset, module, and media relationships. Unknown EOS fields and commands are preserved and may generate warnings. A failed build does not replace the last successful `eosscript.json`.

If sources do not define an EOS `start`, Build generates one Goto to the Outline entry scene's entry Page. An authored `start` is preserved.

## Structural equivalence

Every JSON-compatible EOSScript structure can be represented canonically in Milo YAML:

- EOS top-level fields live in `milo.yaml`;
- the complete `pages` mapping is divided across scene files without changing Page IDs or command payloads;
- JavaScript and module data remain source strings and mappings;
- shorthand is optional.

For canonical EOS YAML that does not rely on Milo shorthand, state generation, asset materialization, or generated module requirements, rebuilding preserves the parsed EOS data structure. Formatting and mapping key order are not part of the equivalence contract.

## Minimal scene

```yaml
format: milo-ir
scene: opening
entry: start
pages:
  start:
    - say: Hello.
    - end: true
```

A complete executable example is in `examples/milo-ir-golden/`.

## Runtime semantics

These sections define the exact EOS behavior behind the canonical commands and Milo shorthand described above.

### Pages and navigation

Every Page ID is global. A Page contains an ordered list of commands.

```yaml
- goto: next-page
- goto: challenge-*
- disable: challenge-easy
- enable: challenge-*
```

Canonical Goto is written directly as EOS:

```yaml
- goto:
    target: next-page
```

Goto transfers execution immediately, so later commands on the current Page do not run. A wildcard target selects one enabled matching Page at runtime. Enable and disable change which Pages are available to wildcard selection.

If a wildcard has no enabled match, runtime navigation has no valid target. Build warns when a recognizable static pattern has no match. Enable/disable targets with no static match are preserved and may also produce warnings.

Canonical Choice options may target a Page directly or run nested commands. Dynamic navigation through the `pages` JavaScript API cannot be fully checked at Build time; prefer a normal Goto when the target is statically known.

```yaml
- choice:
    options:
      - label: Continue
        commands:
          - goto:
              target: next-page
```

The `pages` API includes:

```javascript
pages.isEnabled(id)
pages.enable(id)
pages.disable(id)
pages.getCurrentPageId()
pages.goto(id)
pages.addEventListener('change', listener)
```

### Prompt

Prompt reads text into a runtime variable. Show the question with Say before requesting input.

```yaml
# milo.yaml
state:
  player_name: null
```

```yaml
- say: What should I call you?
- prompt: player_name
```

Canonical EOS Prompt uses the native runtime variable named by `variable`:

```yaml
- prompt:
    variable: playerName
```

Milo scalar Prompt writes to declared Milo state. Canonical EOS Prompt uses its native runtime variable. Handle empty, invalid, or cancelled input when relevant, and make comparison rules such as case sensitivity explicit.

### Say presentation

Canonical Say supports EOS presentation fields such as `mode`, `align`, `duration`, and `allowSkip`. Timing modes include automatic timing, `pause`, `instant`, `autoplay`, and `custom`. `align` is the native Say alignment control and accepts `left`, `center`, or `right`; do not substitute HTML `text-align` for it. `allowSkip` controls whether applicable waits can be skipped.

**Important timing contract:** `autoplay` and fixed custom duration are not interchangeable. In the EOS Runtime, `mode: autoplay` calculates an approximate reading time from the Say label and uses that calculated timeout. An authored `duration` on the same Say does **not** become the autoplay wait time. Therefore do not author `mode: autoplay` together with `duration` when the duration is meant to be exact.

Use `mode: custom` for explicit timing:

```yaml
- say:
    label: Hold this line for nine seconds.
    mode: custom
    duration: 9s
    allowSkip: true
```

Use `mode: autoplay` only when Runtime-selected reading time is desired, and normally omit `duration`:

```yaml
- say:
    label: Continue after an automatically estimated reading time.
    mode: autoplay
    allowSkip: true
```

`allowSkip: true` permits early continuation; it does not halve, scale, or otherwise redefine a custom duration.

For dense rich-text output, including the reusable precomputed Unicode half-block image-sprite method for Say, read `runtime/say.md`.

### Timers

A Timer delays the command queue or schedules commands for later.

For Milo `wait` and scalar `timer` shorthand syntax, see the Milo IR syntax sections above.

Canonical Timer:

```yaml
- timer:
    duration: 10s
    style: secret
    isAsync: true
    commands:
      - goto:
          target: timeout
```

Canonical Timer fields include `duration`, `style`, `isAsync`, and nested `commands`. Styles are `normal`, `secret`, and `hidden`.

- A synchronous Timer pauses the command queue until it expires.
- An asynchronous Timer allows later Page commands to continue while expiry commands remain scheduled.

Nested Timer commands are ordinary EOS command lists. Re-entry and route changes must not create unintended overlapping timers or unsafe expiry behavior.

Canonical Timer mappings may use EOS-supported duration forms beyond Milo's validated fixed shorthand because canonical payloads are preserved as EOS data.

### Audio

Audio requires the EOS `audio` module. Canonical commands are `audio.play` and `audio.stop`.

```yaml
# milo.yaml
modules:
  audio: {}
```

```yaml
- audio.play:
    locator: file:heartbeat.mp3
    background: true
    volume: 0.6
    loops: 0
    id: heartbeat

- audio.stop:
    locator: file:heartbeat.mp3
```

`audio.play` may specify a locator, volume, loop count, background behavior, and an `id`. Background audio continues across Page changes. A loop count of `0` means continuous looping; the normal default is one play.

An explicit `id` registers a sound for JavaScript control:

```javascript
var sound = Sound.get('heartbeat')
sound.play()
sound.pause()
sound.stop()
sound.seek(20)
sound.setVolume(0.5)
sound.destroy()
```

Sound instances emit `play`, `end`, and `pause` events. Background or infinite audio needs an intentional stop or destroy path.

When canonical audio commands are authored directly, declare `modules.audio`. Milo audio shorthand adds the module automatically.

### Notifications

A Notification is persistent UI that can carry a button, a timer, or both. It remains available across Page changes until removed or handled.

```yaml
# milo.yaml
modules:
  notification: {}
```

```yaml
- notification.create:
    id: warning
    title: Time is running out.
    buttonLabel: Continue
    buttonCommands:
      - goto:
          target: continue-page
    timerDuration: 10s
    timerCommands:
      - goto:
          target: timeout

- notification.remove:
    id: warning
```

Canonical commands are `notification.create` and `notification.remove`. Button commands run when the player selects the button; timer commands run after the notification duration. Both are normal nested command lists.

An explicit notification `id` can be addressed from JavaScript:

```javascript
var notice = Notification.get('warning')
notice.setTitle('Five seconds remain.')
notice.remove()
```

Persistent notifications need an intentional completion or removal path.

When canonical notification commands are authored directly, declare `modules.notification`. Milo notification shorthand adds the module automatically.

For persistent title mutation, same-ID replacement rules, and the reusable hidden-Timer ping-pong frame-animation controller, read `runtime/notification.md`.

### Storage

`teaseStorage` keeps JSON-serializable values across sessions of the same tease and requires the EOS `storage` module.

```yaml
# milo.yaml
modules:
  storage: {}

init: |
  var visits = teaseStorage.getItem('visits') || 0;
  visits += 1;
  teaseStorage.setItem('visits', visits);
```

```javascript
teaseStorage.getItem('key')
teaseStorage.setItem('key', value)
```

Values may be strings, booleans, numbers, serializable objects, or `null`. Use stable purpose-scoped keys and version structured data whose shape may evolve. Treat missing, malformed, old-version, and `null` values safely. Persistence is not automatic game-state serialization.

Use `setItem(key, null)` when clearing a value without relying on an undocumented removal method. Do not clear a known-good save before its replacement data is ready.

### JavaScript

Canonical `init`, `eval.script`, `if.condition`, scriptable EOS fields, and Say `<eval>` expressions use the EOS JavaScript environment. The bundled runtime documents ECMAScript 5.

```yaml
# milo.yaml
init: |
  var score = 0;
  function addScore(value) {
    score += value;
  }
```

```yaml
- eval:
    script: addScore(1);
- if:
    condition: score >= 3
    commands:
      - goto:
          target: success
- say:
    label: 'Score: <eval>score</eval>'
```

Build preserves JavaScript as source text and never executes or rewrites it. Runtime behavior must be tested in Preview.

EOS JavaScript runs inside the host interpreter VM, not directly in the browser `window` event loop. Do **not** assume browser scheduling globals such as `setInterval`, `clearInterval`, `setTimeout`, or `clearTimeout` exist in authored `init`/`eval` code. Use EOS `timer` commands for repeated, delayed, or wall-clock-driven behavior. For persistent Notification animation, read `runtime/notification.md` and use its hidden-Timer + loop-Page pattern; do not replace that runtime loop with a browser timer to reduce Page count.

Available globals include:
| Global | Capability | Module |
| --- | --- | --- |
| `console` | logging | always available |
| `pages` | Page state, navigation, change events | always available |
| `Sound` | registered audio control | `audio` |
| `Notification` | notification control | `notification` |
| `teaseStorage` | persistent serializable values | `storage` |
| `EventTarget` | event listener registration and dispatch | always available |

Use one state model deliberately: Milo scalar state for compact `if`, `set`, and Prompt shorthand; native JavaScript variables for objects, arrays, helper functions, and canonical EOS code. Do not assume a Milo state entry and a native variable with the same name are synchronized.

Event-emitting runtime objects follow the `EventTarget` contract:

```javascript
target.addEventListener(type, listener)
target.removeEventListener(type, listener)
target.dispatchEvent(event)
```

### Runtime checks

- Static targets exist and wildcard pools retain a usable target.
- Nested commands remain safe after Page changes.
- Required modules are declared when canonical module commands are authored directly.
- Dynamic navigation has a safe fallback.
- Persistent UI and background audio have intentional cleanup paths.
- JavaScript paths are exercised in Preview because Build validates surrounding structure, not script behavior.
