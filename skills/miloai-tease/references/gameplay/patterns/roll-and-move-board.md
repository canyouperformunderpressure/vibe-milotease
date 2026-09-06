# Roll-and-Move Board

## Design profile

- **Role:** Anchor pattern
- **Best for:** visible forward progress, chance, anticipation, setbacks, special spaces
- **Typical scale:** phase / whole work
- **Can lead a phase:** Yes
- **Player mainly:** roll or draw movement, advance a position, resolve the landed space, then repeat until a finish condition
- **Combines well with:** `random-encounters.md`, `progression.md`, `random-pool-control.md`, `timed-challenge.md`, `content-gating.md`, `unlock-codes.md`, `save-resume.md`


A roll-and-move board turns one numeric or ordered position into the main progression state. Each cycle produces movement, updates the position, resolves any special-space rule, runs the landed-space content, and returns to the movement step.

The pattern describes the board loop itself. It does not prescribe a visual board, a particular setting, a specific die size, or a fixed set of challenges.

## Core loop

```text
roll / draw movement
→ update position
→ resolve movement effects or special space
→ resolve ordinary or special content
→ return to movement
→ finish when the terminal condition is satisfied
```

## Core model

Keep the board state small:

```javascript
var position = 0;
var trackLength = 100;
var lastMove = 0;
```

Optional additions should exist only when they affect later behavior:

- a turn counter;
- section/tier derived from position;
- reusable special-space metadata;
- a limited resource consumed by board events;
- persistent progress when the board spans sessions.

Do not create one state variable for every board space unless those spaces genuinely carry persistent state.

## Minimal movement

```javascript
function rollMovement() {
  return Math.floor(Math.random() * 6) + 1;
}

function advancePosition(amount) {
  lastMove = amount;
  position += amount;
}
```

The movement source may be a die, cards, a weighted roll, a player choice, or another random pool. The board pattern only requires that it produce a movement result.

## Space resolution

Resolve space behavior after movement. Keep three concerns distinct:

1. **Movement effects** — immediately change position again, such as advance, setback, shortcut, or slide.
2. **Special spaces** — enter authored challenge or decision content.
3. **Ordinary spaces** — resolve the default encounter/activity and continue.

Conceptually:

```javascript
function resolvePosition() {
  if (position >= trackLength) return "finish";
  if (isMovementEffect(position)) return "movement-effect";
  if (isSpecialSpace(position)) return "special-space";
  return "ordinary-space";
}
```

Avoid mixing every special-space rule into one long dispatcher when the board becomes large. Use a small routing table, helper functions, or dedicated Pages when that is clearer.

## Milo IR skeleton

```yaml
pages:
  board-turn:
    - eval:
        script: |
          lastMove = Math.floor(Math.random() * 6) + 1;
          position += lastMove;
    - say:
        label: "<p>Moved <eval>lastMove</eval>. Position: <eval>position</eval>.</p>"
    - goto: board-resolve

  board-resolve:
    - if:
        position >= 100: board-finish
    - if:
        position == 12: board-shortcut
    - if:
        position == 27: special-challenge
    - goto: ordinary-space-*

  board-shortcut:
    - eval:
        script: position = 34
    - say: Move forward to position 34.
    - goto: ordinary-space-*

  special-challenge:
    - choice:
        - label: Accept challenge
          to: special-challenge-play
        - label: Decline and move back
          commands:
            - eval:
                script: position = 22
          to: ordinary-space-*

  special-challenge-play:
    - say: Resolve the authored challenge here.
    - eval:
        script: position = 32
    - goto: ordinary-space-*

  ordinary-space-a:
    - say: Resolve an ordinary board event.
    - goto: board-turn

  ordinary-space-b:
    - say: Resolve another ordinary board event.
    - goto: board-turn

  board-finish:
    - goto: finale
```

The numeric positions and rewards above are placeholders. A project defines its own track length and space map.

## Special challenge spaces

A useful special-space form is a risk/reward gate:

```text
land on special space
→ explain the challenge and stakes
→ accept or decline
→ decline = authored setback or alternate route
→ success = authored reward or advancement
→ return to board loop
```

This works well because the challenge changes board state instead of feeling detached from the main game. Keep the consequence proportional enough that accepting the challenge remains a meaningful decision rather than an obvious mandatory choice.

Do not create a separate `challenge-gate` pattern merely because one board uses this form. Split it out only when the same accept/decline/reward structure becomes broadly useful outside board play.

## Escalation by position

The current position can double as a progression signal. For example:

```javascript
function boardTier() {
  if (position < 25) return "early";
  if (position < 70) return "middle";
  return "late";
}
```

An ordinary encounter may then change pace, duration, difficulty, event pool, or available choices by tier.

Prefer deriving the tier from `position` when position already expresses progress. Do not maintain a second stage counter unless it can diverge for a real design reason.

Read `progression.md` when board advancement unlocks persistent behavior beyond the immediate landed space.

## Ordinary-space encounters

When many ordinary spaces share the same gameplay purpose, do not author a unique Page for every number. Route to a reusable encounter pool:

```yaml
- goto: ordinary-space-*
```

Then let the selected encounter read the current position or board tier before returning to `board-turn`.

Read `random-encounters.md` and `random-pool-control.md` when ordinary spaces need variety, no-repeat behavior, weighting, cooldowns, or guarantees.

## Limited resources

A board may include a small resource that changes how the player can react to events:

```javascript
var charges = 3;

function spendCharge() {
  if (charges <= 0) return false;
  charges--;
  return true;
}

function addCharge(amount) {
  charges += amount;
}
```

Useful compositions include:

- spend a charge to recover, reroll, avoid a setback, or exit a challenge;
- gain a charge from a rare movement result or reward space;
- change the fallback behavior when charges reach zero.

Keep this subordinate to the board unless resource management itself becomes the main player activity. If it only modifies the board loop, it does not need its own pattern file.

## Finish and overshoot rules

Define the finish rule explicitly:

- finish at or beyond the final position;
- require an exact roll;
- bounce or clamp overshoot;
- route overshoot to another authored effect.

Do not leave overshoot behavior implicit. It can materially change game length and player frustration.

The finish may route to one finale, a choice among finales, a random finale pool, or an unlock-code route. Read `unlock-codes.md` when a secret input exposes an authored ending or reward.

## Composition guidance

- **Board + random encounters:** ordinary spaces use a random event pool.
- **Board + progression:** later positions raise difficulty or unlock new pools.
- **Board + timed challenge:** special spaces contain measurable short challenges.
- **Board + content gating:** optional event categories are removed from eligible pools or special-space routes.
- **Board + save/resume:** persist stable board position and supporting state between sessions.

The board should remain the anchor. If the player spends most of the phase navigating a spatial world, use `map-exploration.md`; if the player mostly resolves unrelated random events without meaningful track position, use `random-encounters.md` instead.

## Check

- Movement always produces a valid next state.
- Every movement effect has a defined destination and cannot create an accidental infinite chain.
- Special spaces have explicit success, decline/failure, and return behavior.
- Ordinary spaces reliably return to the board loop unless intentionally branching out.
- Position-based escalation has no unreachable gaps or contradictory ranges.
- Required progress is not blocked indefinitely by randomness without an intentional design reason.
- Limited resources cannot become negative unless negative values have explicit meaning.
- Finish and overshoot behavior are explicit.
- Project-specific characters, themes, locations, content categories, and endings remain outside the reusable board pattern.
