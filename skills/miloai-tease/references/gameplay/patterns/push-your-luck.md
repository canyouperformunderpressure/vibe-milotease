# Push Your Luck

## Design profile

- **Role:** Anchor or scene pattern
- **Best for:** temptation, escalating risk, greed versus safety, suspense, voluntary commitment
- **Typical scale:** scene / phase
- **Can lead a phase:** Yes
- **Player mainly:** repeatedly choose whether to bank current gains or risk them for another chance at a better result
- **Combines well with:** `lottery.md`, `deck-draw.md`, `quiz-challenge.md`, `resource-economy.md`, `progression.md`


Push-your-luck gameplay creates a recurring voluntary decision between **stop safely now** and **continue for more while risking what is currently unbanked**. Randomness alone is not enough; the player's choice to continue under known stakes is the heart of the pattern.

## Core loop

```text
gain or expose a pending reward
→ show current stakes
→ choose bank / stop or continue
→ continuing resolves uncertainty
→ safe result increases pending value or pressure
→ bust/failure reduces or loses pending value
→ return to the choice while still eligible
```

If the player cannot choose when to stop, use `lottery.md`, `deck-draw.md`, or another random pattern instead.

## Minimal state

```yaml
# milo.yaml
state:
  pendingValue: 0
  bankedValue: 0
  pushes: 0
```

Keep **pending** and **banked** value separate. The tension comes from risking something the player could preserve by stopping.

## Minimal loop

```yaml
pages:
  push-choice:
    - say: "Pending value: <eval>pendingValue</eval>. Bank it, or risk another draw?"
    - choice:
        Bank: push-bank
        Continue: push-roll

  push-roll:
    - set: pushes += 1
    - if:
        pushes >= 4: push-roll-high-risk
        else: push-roll-normal

  push-roll-normal:
    - random:
        push-safe: 75
        push-bust: 25

  push-roll-high-risk:
    - random:
        push-safe: 55
        push-bust: 45

  push-safe:
    - set: pendingValue += 1
    - say: Safe. The pending value increases.
    - goto: push-choice

  push-bank:
    - set: bankedValue += pendingValue
    - set: pendingValue = 0
    - set: pushes = 0
    - goto: push-finish

  push-bust:
    - set: pendingValue = 0
    - set: pushes = 0
    - say: The pending value is lost.
    - goto: push-finish
```

The numbers above are placeholders. Tune risk and reward for the desired session length and emotional arc.

## What can escalate

Risk does not have to mean only a higher bust percentage. Continuing may instead:

- increase the value at stake;
- add stronger outcomes to the pool;
- remove safe cards from a deck;
- make the next quiz question harder;
- increase time pressure;
- reduce available escape or recovery resources.

Escalation should be legible enough that “continue” is a meaningful decision. Hidden probability changes are possible, but if the player cannot perceive any change in stakes, the choice may feel arbitrary rather than tense.

## Banking rules

Decide exactly what “stop” preserves:

- all pending value;
- only part of it;
- a checkpoint or milestone;
- one reward while forfeiting another;
- progress but not temporary bonuses.

Likewise, define bust behavior explicitly. Losing everything is not required. A bust can halve pending value, add a setback, end only the current round, or convert the result into another consequence.

The consequence must be large enough to create tension but not so large that rational play always means stopping immediately.

## Fixed odds versus depleting risk

With `lottery.md`, each attempt may use the same independent odds. With `deck-draw.md`, each draw changes the remaining composition, allowing the player to reason from what has already appeared.

These create different experiences:

- **Fixed odds:** simple, fast, easy to tune.
- **Depleting deck:** more memory, inference, and visible changing risk.

Do not maintain both a deck composition and an unrelated hidden risk percentage unless both matter to player decisions.

## Checkpoints and multiple rounds

A longer phase can use several push-your-luck rounds:

```text
round 1: build and bank
→ checkpoint
round 2: higher base stakes
→ checkpoint
final round: optional high-risk conversion
```

Banked value can feed `progression.md` or `resource-economy.md`. Reset only the temporary state between rounds.

## Composition guidance

- **Push-your-luck + lottery:** each continue action rolls independent safe/bust odds.
- **Push-your-luck + deck:** the remaining deck makes risk evolve after every draw.
- **Push-your-luck + quiz:** bank a streak/reward or risk it on another harder question.
- **Push-your-luck + economy:** spend a limited resource to insure, reroll, or soften a bust.
- **Push-your-luck + progression:** later stages raise base stakes or unlock safer/harder variants.

Use `surrender-option.md` when the concern is preserving an emergency way out of an ongoing challenge. A push-your-luck “bank” choice is not surrender: it is a normal strategic exit that converts pending state into a safer result.

## Check

- The player can intentionally choose between stopping and continuing.
- The current pending stakes are understandable before the decision.
- Banking and busting update pending/banked state exactly once.
- Continuing changes expected value, risk, or consequence enough to stay meaningful.
- The safest action is not trivially dominant from the first decision unless that is intentional.
- Risk escalation has bounded states and cannot run forever accidentally.
- A completed round has an explicit reset, checkpoint, or exit.
- Randomness comes from the appropriate underlying pattern: independent pool or depleting deck.
