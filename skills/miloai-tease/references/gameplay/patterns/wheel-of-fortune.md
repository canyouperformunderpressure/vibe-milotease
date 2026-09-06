# Wheel of Fortune

## Design profile

- **Role:** Anchor pattern
- **Best for:** recurring uncertainty, visible suspense, changing rules or intensity, phase-long random control
- **Typical scale:** scene / phase
- **Can lead a phase:** Yes
- **Player mainly:** keep playing under the current wheel result, then periodically spin again and adapt to the next result
- **Combines well with:** `timed-challenge.md`, `metronome-stroking.md`, `self-control-challenge.md`, `progression.md`, `random-pool-control.md`


Wheel of Fortune is a **repeating random-mode loop** built around a stable set of visible wheel sectors. The wheel repeatedly selects which rule, instruction family, pace, constraint, or temporary mode controls play next.

The defining structure is not merely “pick a random outcome.” A Wheel of Fortune phase has a recognizable rhythm:

```text
play under current mode
→ spin
→ reveal one wheel sector
→ apply that sector's rule or instruction
→ continue for a bounded interval or until a condition is met
→ spin again
→ repeat until the phase ends
```

The wheel may be represented by a literal wheel, an animation, a sequence of images, sound, or another clear spin-and-reveal presentation. The reusable gameplay pattern is the repeated sector-driven mode change.

## Why this is not Lottery

Use `lottery.md` when the mechanic is primarily:

```text
trigger draw
→ select one independent result
→ resolve that result
→ leave or draw again
```

Use Wheel of Fortune when **the same wheel repeatedly controls an ongoing activity**:

- the wheel has a stable set of recognizable sectors or sector categories;
- sector proportions or weights are part of the design;
- the player remains inside the same larger activity while results change its current rules;
- the selected result usually persists for a while rather than immediately ending in a separate result scene;
- repeated spins create the phase's pacing and escalation;
- the wheel may switch to a different sector table for another stage, finale, or mode.

A one-shot prize wheel can still use this pattern, but it is a secondary variant. If removing the wheel presentation leaves only a generic independent result draw, prefer `lottery.md`.

## Core loop

```text
initialize phase duration / finish condition
→ establish a starting activity or pace
→ spin wheel
→ choose sector according to wheel proportions
→ reveal sector
→ apply its mode or instruction family
→ run that mode for a short interval or until its completion condition
→ if phase is still active, spin again
→ otherwise enter the finishing step or final wheel
```

The wheel should normally be the **dispatcher for an ongoing phase**, not a collection of unrelated destination Pages.

## Stable sectors and explicit proportions

Design the wheel as a fixed composition of sectors. A simple ten-sector wheel might be:

```text
3 × Intensify
3 × Ease
3 × Wildcard
1 × Checkpoint
```

That produces category probabilities of 30% / 30% / 30% / 10% while still feeling like one physical ten-sector wheel.

The implementation may select one of ten logical positions and map positions to categories:

```text
positions 1, 2, 9   → Intensify
positions 3, 4, 10  → Ease
positions 5, 6, 7   → Wildcard
position 8          → Checkpoint
```

This is preferable to describing the wheel only as abstract percentages when the player is meant to understand its visible layout.

If the visual wheel uses unequal physical sectors, reproduce those odds deliberately in logic. Do not let asset count or animation timing accidentally determine probability.

## Result as a temporary mode

The selected sector usually changes **how the current activity works** until the next spin.

Useful sector effects include:

- increase or decrease a pace, target, rate, or difficulty;
- impose a temporary behavioral rule;
- switch to another instruction family;
- request a checkpoint or player-confirmed milestone;
- temporarily add a second task or restriction;
- alter a multiplier or other short-lived control value.

Keep the wheel result separate from the exact wording shown to the player. One sector category can have a pool of varied instructions while preserving the same mechanical meaning.

For example:

```text
wheelMode = Intensify
→ choose one Intensify instruction
→ apply its pace/rule change
→ continue play
```

This gives variation without turning every line of dialogue into a different wheel sector.

## Phase timer or finish condition

A strong Wheel of Fortune phase often runs under an **overall duration or progress goal** independent of the individual spin intervals.

```text
phase starts
→ set phaseEndAt
→ run repeated spin cycles
→ after each cycle, check remaining phase time
→ continue while active
→ leave the loop when the overall phase ends
```

Individual results may last for different amounts of time. The important distinction is that the outer phase timer controls when the wheel game finishes, while each spin controls what happens inside the phase.

This lets the wheel feel continuous instead of like a sequence of disconnected mini-scenes.

## Spin presentation

A spin should create a brief boundary between modes:

```text
announce spin
→ play wheel sound / animation
→ wait for the spin presentation
→ determine or reveal the sector
→ announce the new mode
```

The logical result may be chosen before, during, or immediately after the animation. What matters is that probability comes from game logic and the reveal agrees with the stored result.

Do not require a large frame-by-frame animation for the pattern to count as Wheel of Fortune. Presentation should support the repeated decision rhythm, not dominate the implementation.

## Different wheel tables by phase

The same authored wheel can use a different result table when the purpose changes.

For example, the main phase might use:

```text
30% Intensify
30% Ease
30% Wildcard
10% Checkpoint
```

Then a finishing wheel might instead use:

```text
6 / 12 → favorable finish
4 / 12 → mixed finish
2 / 12 → unfavorable finish
```

This is still one Wheel of Fortune pattern because the player understands that the wheel is the decision mechanism; only the **sector table and semantic meaning** change for the new phase.

Use explicit state such as `wheelPhase` or separate selection functions when multiple tables exist. Do not hide table switching inside unrelated dialogue conditions.

## Repeat behavior

Immediate repeats are **allowed by default**. A real wheel can land on the same category twice, and repeated results can be part of the tension.

Only add no-repeat behavior when the design specifically needs more variety. If repeat suppression, cooldowns, guarantees, or dynamic weighting become important, compose with `random-pool-control.md`.

Do not treat `lastWheelResult` as mandatory Wheel of Fortune state.

## Minimal state model

Typical state is small:

```yaml
state:
  wheelMode: 0
  wheelPhase: main
  wheelSpins: 0
```

The outer phase may additionally track a timer, progress counter, or finish flag.

Only persist exact wheel state across sessions when resuming mid-phase actually matters.

## Escalation

A Wheel of Fortune phase can escalate without changing its basic loop:

- increase the base intensity that sector effects modify;
- make positive/negative modifiers stronger later;
- shorten the time between spins;
- change the sector table at a milestone;
- unlock a rarer sector category;
- transition from a repeated control wheel to a one-spin finishing wheel.

Use `progression.md` when these changes depend on explicit stages or milestones.

## Secondary variant: one-shot settlement wheel

A wheel may also be used once to select a reward, penalty, movement, resource change, or other settlement effect.

That variant is valid, but it should not define the core reference. Use it when the visible wheel and stable sectors materially matter. If the mechanic is only independent random selection with no meaningful wheel structure, use `lottery.md` instead.

## Composition guidance

- **Wheel + timed challenge:** an outer duration controls how long the repeated wheel loop runs.
- **Wheel + metronome:** wheel sectors alter the current pace or rhythm until the next spin.
- **Wheel + self-control challenge:** sectors temporarily change the rule the player must obey.
- **Wheel + progression:** later stages change the sector table, effect strength, or finishing rules.
- **Wheel + random-pool control:** add deliberate no-repeat, cooldown, dynamic weighting, or guarantees only when required.

Keep modifiers subordinate to the spin loop. The player should always understand what the current sector means and when another spin will occur.

## Check

- The wheel has a stable, understandable sector composition.
- Sector proportions in logic match the intended wheel proportions.
- The current sector changes an ongoing activity rather than merely renaming a random branch.
- Each spin has a clear reveal and a bounded period before the next spin or exit.
- The outer phase has an explicit duration, progress goal, or finish condition.
- Repeated spins cannot accidentally continue forever after the phase should end.
- Repeated results are intentionally allowed or intentionally controlled.
- If multiple wheel tables exist, the active table is explicit and tied to the current phase.
- Presentation does not accidentally determine probability.
- If the wheel is only cosmetic independent random selection, prefer `lottery.md`.
