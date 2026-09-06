# Lottery

## Design profile

- **Role:** Anchor or scene pattern
- **Best for:** anticipation, uncertainty, risk/reward
- **Typical scale:** scene / phase
- **Can lead a phase:** Yes
- **Player mainly:** draw or trigger an outcome, then deal with the selected result
- **Combines well with:** `random-pool-control.md`, `progression.md`


A Lottery sends the player to one result selected from a pool. Results may return to the draw, open another route, or end.

### Minimal equal-probability pool

Use one Page prefix and wildcard Goto:

```yaml
pages:
  lottery:
    - say: Draw a card.
    - goto: lottery-result-*

  lottery-result-common:
    - say: A common result.
    - choice:
        Draw again: lottery
        Leave: exit

  lottery-result-special:
    - say: A special result.
    - goto: special-route

  special-route:
    - say: The special route begins.
    - end: true

  exit:
    - end: true
```

Wildcard Goto chooses one enabled matching Page. Every result needs an explicit exit; it does not return to the pool automatically.

### Weighted results

Use `random` when results need different probabilities:

```yaml
- random:
    lottery-result-common: 80
    lottery-result-special: 20
```

Weights are positive relative values and do not need to total 100.

### State and external routes

A result may update state before returning:

```yaml
- set: draws += 1
- goto: lottery
```

It may also enter another Outline node with `$node-id` when the current Outline node permits that edge.

### Check

- The pool pattern matches at least one Page.
- Every result reaches another draw, another route, or an intentional end.
- Required progression is not left to an unbounded random wait.
- State used by results is declared in `milo.yaml.state`.

For no-repeat, cooldown, and guarantees, read `random-pool-control.md` alongside this reference.
