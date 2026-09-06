# Unlock codes

## Design profile

- **Role:** Support / reward pattern
- **Best for:** unlocking, shortcuts, secrets, return-player rewards
- **Typical scale:** scene / whole work
- **Can lead a phase:** No
- **Player mainly:** enter a code to restore or expose authored content
- **Combines well with:** `progression.md`, `save-resume.md`


An unlock code maps player input to a known route or flag. It may grant a reward, restore a milestone, expose an authored debug route, or create a permanent unlock.

### Session code

```yaml
# milo.yaml
state:
  enteredCode: ''
```

```yaml
pages:
  code-entry:
    - say: Enter the code exactly as shown.
    - prompt: enteredCode
    - if:
        enteredCode == 'ALPHA-42': reward
        else: code-incorrect

  code-incorrect:
    - say: The code was not recognized.
    - goto: code-entry
```

Compact comparison is exact and case-sensitive. If the work accepts trimmed or case-insensitive input, normalize it explicitly with canonical JavaScript and explain the rule to the player.

### Permanent unlock

```yaml
# milo.yaml
modules:
  storage: {}

init: |
  var bonusUnlocked = teaseStorage.getItem('unlock:bonus') === true;
```

```yaml
- eval:
    script: |
      bonusUnlocked = true;
      teaseStorage.setItem('unlock:bonus', true);
```

Use a Boolean for a permanent unlock. For a one-use code, persist a consumed flag before entering the reward route.

An authored debug menu is not a security boundary. Do not place credentials or external-service secrets in a tease code.

### Check

- Valid, invalid, empty, and repeated inputs have defined behavior.
- Error messages do not reveal all valid codes unless intended.
- Permanent unlocks load before their visibility conditions run.
- One-use codes record consumption before the reward begins.
- Every unlocked external route is permitted by the Outline graph.
