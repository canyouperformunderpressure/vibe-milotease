# Timed challenge

## Design profile

- **Role:** Anchor or modifier pattern
- **Best for:** pressure, urgency, endurance, performance
- **Typical scale:** scene / phase
- **Can lead a phase:** Yes
- **Player mainly:** complete or endure an instruction before a deadline
- **Combines well with:** `metronome-stroking.md`, `dual-task-challenge.md`, `retry-loop.md`, `surrender-option.md`


A timed challenge runs an instruction, choice, or sequence for a fixed window and may take a timeout route.

### Fixed wait

For a fixed interval with no interaction, the gameplay pattern only needs a wait:

```yaml
- say: Hold this position.
- wait: 20s
- goto: completed
```

### Deadline with input

When the player must still be able to respond before a deadline expires, use the runtime Timer capability to schedule the timeout route while keeping the choice available:

```yaml
# milo.yaml
init: |
  var challengeActive = false;

# Scene source
pages:
  challenge:
    - eval:
        script: challengeActive = true;
    - say: Finish before time runs out.
    - timer:
        duration: 15s
        style: secret
        isAsync: true
        commands:
          - if:
              condition: challengeActive === true
              commands:
                - eval:
                    script: challengeActive = false;
                - goto:
                    target: timeout
    - choice:
        options:
          - label: Completed
            commands:
              - eval:
                  script: challengeActive = false;
              - goto:
                  target: success
          - label: Stop
            commands:
              - eval:
                  script: challengeActive = false;
              - goto:
                  target: stopped

  success:
    - say: Completed in time.
    - end: true

  stopped:
    - say: The challenge stops.
    - end: true

  timeout:
    - say: Time ran out.
    - end: true
```

The active flag makes an expired Timer a no-op after the player has already selected a route. Any other state changes or persistent UI touched by these paths must follow the same rule. The exact `timer` fields and sync/async execution semantics are defined only in `../../implementation.md`.

### Paced stages with audio

```yaml
# milo.yaml
assets:
  steady-beat: media/sources/audio/steady-beat.mp3
```

```yaml
- audio:
    asset: steady-beat
    action: play
    id: challenge-beat
    loops: 0
- wait: 20s
- audio:
    asset: steady-beat
    action: stop
- goto: next-stage
```

Use separate Pages when stages have different instructions, exits, media, or cleanup behavior.

### Check

- Timeout, success, stop, and skip targets exist when offered.
- Timeout behavior remains safe after Page changes.
- Re-entry does not leave overlapping Timers, background audio, or persistent UI.

Load `../../implementation.md` for Timer API details or exact audio lifetime behavior.
