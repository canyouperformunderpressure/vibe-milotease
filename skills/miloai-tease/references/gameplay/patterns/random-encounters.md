# Random encounters

## Design profile

- **Role:** Anchor pattern
- **Best for:** variety, unpredictability, replayability
- **Typical scale:** phase
- **Can lead a phase:** Yes
- **Player mainly:** resolve a sequence of encounters selected from an event set
- **Combines well with:** `random-pool-control.md`, `progression.md`, `map-exploration.md`


A random-encounter loop selects a short event, resolves it, and returns to a shared dispatcher. The loop may track rounds or change the available event set as progression advances.

### Minimal loop

```yaml
# milo.yaml
state:
  rounds: 0
```

```yaml
# src/<node>.milo.yaml
pages:
  encounter-loop:
    - random:
        encounter-observe: 3
        encounter-choice: 2
        encounter-special: 1

  encounter-observe:
    - say: Observe the scene.
    - goto: encounter-done

  encounter-choice:
    - choice:
        Safe route: encounter-done
        Risky route: consequence

  encounter-special:
    - goto: special-sequence

  consequence:
    - say: Resolve the risky choice.
    - goto: encounter-done

  special-sequence:
    - say: Resolve the special sequence.
    - goto: encounter-done

  encounter-done:
    - set: rounds += 1
    - if:
        rounds >= 8: finale
        else: encounter-loop

  finale:
    - end: true
```

Events may return directly to the dispatcher, but a shared completion Page is useful when every event updates the same progression state.

### Event groups

Use a wildcard pool when all matching events should have equal probability:

```yaml
- goto: encounter-low-*
```

Use separate dispatchers for different stages rather than keeping every event in one permanent pool. `enable` and `disable` can temporarily change which wildcard results remain available.

Independent encounters do not require narrative or visual continuity with one another unless the design explicitly guarantees an order.

### Check

- The dispatcher always has an available target.
- Every encounter has an intentional return or exit.
- A finite loop has an explicit transition or ending condition.
- External `$node` routes are declared in the current Outline node's `next` list.
