# Progression

## Design profile

- **Role:** Support / progression pattern
- **Best for:** growth, escalation, visible or hidden advancement
- **Typical scale:** phase / whole work
- **Can lead a phase:** Usually no
- **Player mainly:** accumulate completion, unlock later content, or move through stages
- **Combines well with:** almost any anchor pattern


Progression records which stage the player is in and which content has been completed. Keep only state that changes later behavior.

### Session progression

```yaml
# milo.yaml
state:
  stage: 1
  completed: 0
  bonusUnlocked: false
```

```yaml
pages:
  event-complete:
    - set: completed += 1
    - if:
        completed >= 3: advance-stage
        else: hub

  advance-stage:
    - set: stage += 1
    - set: completed = 0
    - set: bonusUnlocked = true
    - enable: bonus-*
    - goto: hub
```

Typical models are:

- `stage` for chapter, day, tier, or phase;
- a completion counter toward the next transition;
- Boolean flags for one-time events or important unlocks;
- native JavaScript objects only when many structured flags make scalar Milo state awkward.

Milestones should normally be conditions over existing progress rather than introducing a second competing counter.

### Re-entry and persistence

Make one-time completion idempotent when the same Page can be revisited. A repeatable event may intentionally increment on every visit.

Session state resets with a new session. Read `save-resume.md` when progression must persist across sessions.

### Check

- Every state value is initialized before use.
- Repeating a Page has the intended effect.
- Stage transitions have reachable inputs and outputs.
- Locked content has an unlock path.
- Progress reaches a finale, reset, or intentional repeatable state.
