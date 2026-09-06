# Settings

## Design profile

- **Role:** Support pattern
- **Best for:** player control over presentation or difficulty
- **Typical scale:** whole work
- **Can lead a phase:** No
- **Player mainly:** choose persistent or session-level configuration
- **Combines well with:** any gameplay whose parameters genuinely change


Settings change presentation, difficulty, or available content without redefining the source graph. Define only settings the work actually uses.

### Session settings

```yaml
# milo.yaml
state:
  difficulty: standard
  voiceEnabled: true
```

```yaml
# src/settings.milo.yaml
format: milo-ir
scene: settings
entry: settings

pages:
  settings:
    - choice:
        - label: Standard difficulty
          commands:
            - set: difficulty = 'standard'
          to: settings
        - label: Hard difficulty
          commands:
            - set: difficulty = 'hard'
          to: settings
        - label: Enable voice
          to: settings-voice-on
        - label: Disable voice
          to: settings-voice-off
        - label: Continue
          to: $opening

  settings-voice-on:
    - set: voiceEnabled = true
    - goto: settings

  settings-voice-off:
    - set: voiceEnabled = false
    - goto: settings
```

`$opening` must be an allowed Outline exit from the `settings` node.

Use the setting later with normal state conditions:

```yaml
- if:
    voiceEnabled: intro-with-voice
    else: intro-without-voice
```

### Persistence

Keep temporary choices in Milo state. Use storage only when a preference should survive a new session, then validate loaded values and provide a reset path.

### Check

- Defaults produce a playable work without visiting Settings.
- Every offered value changes behavior somewhere.
- Hidden content cannot be reached through an unintended route.
- Difficulty changes parameters or routes consistently.
- Persistent settings can be reset.
