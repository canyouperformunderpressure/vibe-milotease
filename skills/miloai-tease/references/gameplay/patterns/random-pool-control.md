# Random pool control

## Design profile

- **Role:** Modifier pattern
- **Best for:** controlled surprise, fairness, variety without bad repetition
- **Typical scale:** scene / phase
- **Can lead a phase:** Usually no
- **Player mainly:** experiences a curated random sequence rather than raw independent rolls
- **Combines well with:** `lottery.md`, `random-encounters.md`


Choose the simplest pool behavior that satisfies the design.

### Equal probability

```yaml
- goto: event-*
```

This has no weights, history, cooldown, or guarantee.

### Weighted probability

```yaml
- random:
    event-common: 80
    event-rare: 20
```

### No repeat within a cycle

Disable a selected Page before returning to the pool:

```yaml
pages:
  event-a:
    - disable: event-a
    - say: Event A.
    - goto: pool
```

Re-enable the group when a new cycle begins:

```yaml
- enable: event-*
- goto: pool
```

Do not exhaust every result without a reset or fallback.

### Guaranteed result after misses

Use a counter to force an important result after a known number of misses:

```yaml
# milo.yaml
state:
  misses: 0
```

```yaml
pages:
  pool:
    - if:
        misses >= 4: event-rare
        else: pool-roll

  pool-roll:
    - set: misses += 1
    - random:
        event-common-a: 1
        event-common-b: 1

  event-rare:
    - set: misses = 0
    - goto: rare-content
```

Cooldowns use the same idea with explicit counters or state plus `enable` and `disable`.

### Check

- Every target exists.
- At least one result remains available.
- State updates happen before returning to the dispatcher.
- Reset behavior is explicit.
- Progress that must happen has a deterministic fallback.
