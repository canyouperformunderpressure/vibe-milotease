# Maze

## Design profile

- **Role:** Anchor pattern
- **Best for:** exploration, spatial uncertainty, discovery, gating
- **Typical scale:** phase / multi-scene
- **Can lead a phase:** Yes
- **Player mainly:** navigate between locations, remember routes, find access conditions
- **Combines well with:** `random-encounters.md`, `progression.md`, `save-resume.md`


A Maze represents each room or location as a Page. Player choices are directed edges between Pages.

### Map first

Design the room graph before dialogue or media:

```text
entrance → hall ↔ key-room
             ↓
          locked-exit → success
```

Then implement the same graph:

```yaml
# milo.yaml
state:
  hasKey: false
```

```yaml
pages:
  maze-entrance:
    - choice:
        North: maze-hall

  maze-hall:
    - choice:
        South: maze-entrance
        East: maze-key-room
        North: maze-locked-exit

  maze-key-room:
    - say: You found the key.
    - set: hasKey = true
    - goto: maze-hall

  maze-locked-exit:
    - if:
        hasKey: success
        else: maze-locked

  maze-locked:
    - say: The exit is locked.
    - goto: maze-hall

  success:
    - end: true
```

### Variations

- Use state to unlock, hide, or change exits.
- Track steps or visited rooms only when later behavior needs that information.
- Put repeatable room events behind a local dispatcher when a room contains random content.
- Add persistence only when the Maze must continue across sessions.

### Check

- Every direction points to an existing Page.
- Required items and the exit are reachable.
- Conditional exits handle both satisfied and unsatisfied states.
- Loops do not trap the player unintentionally.
- The Maze has an intentional exit, reset, or deliberate endless-loop design.
