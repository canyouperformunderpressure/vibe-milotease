# Save and resume

## Design profile

- **Role:** Support / persistence pattern
- **Best for:** continuity across sessions
- **Typical scale:** whole work
- **Can lead a phase:** No
- **Player mainly:** resume from stable checkpoints with reconstructed state
- **Combines well with:** long-form `maze.md`, `map-exploration.md`, `progression.md`, or episodic designs


A save stores stable game data across sessions and resumes from a known checkpoint. Use the EOS `storage` module and `teaseStorage` API.

### Data shape

Keep one versioned object:

```javascript
{
  version: 1,
  checkpoint: 'chapter-hub',
  score: 4,
  unlocked: {bonus: true}
}
```

Save only data needed to reconstruct the experience. Do not store active Timer handles, Sound objects, Notification objects, or a position inside a command queue.

### Runtime setup

```yaml
# milo.yaml
modules:
  storage: {}

init: |
  var score = 0;
  var unlocked = {bonus: false};
  var saveKey = 'main-save';

  function readSave() {
    return teaseStorage.getItem(saveKey);
  }

  function hasSave() {
    var data = readSave();
    return data && data.version === 1;
  }

  function saveGame(checkpoint) {
    teaseStorage.setItem(saveKey, {
      version: 1,
      checkpoint: checkpoint,
      score: score,
      unlocked: unlocked
    });
  }

  function restoreGame() {
    var data = readSave();
    var allowed = {'chapter-hub': true, 'chapter-two': true};
    if (!data || data.version !== 1) return false;
    score = typeof data.score === 'number' ? data.score : 0;
    unlocked = data.unlocked || {bonus: false};
    pages.goto(allowed[data.checkpoint] ? data.checkpoint : 'chapter-hub');
    return true;
  }

  function resetGame() {
    teaseStorage.setItem(saveKey, null);
    score = 0;
    unlocked = {bonus: false};
  }
```

Use only documented storage operations. Clearing with `null` avoids relying on an undocumented removal method.

### Start and checkpoint

```yaml
pages:
  start:
    - if:
        condition: hasSave()
        commands:
          - choice:
              options:
                - label: Continue
                  commands:
                    - eval:
                        script: restoreGame();
                - label: New game
                  commands:
                    - eval:
                        script: resetGame();
                    - goto:
                        target: opening
        elseCommands:
          - goto:
              target: opening

  chapter-hub:
    - eval:
        script: saveGame('chapter-hub');
    - say: Progress saved.
```

Save after the state change that defines the checkpoint. Restore temporary UI, enabled pools, and background audio after loading instead of trying to serialize their runtime objects.

### Version changes

When the save shape changes, accept known old versions and fill new defaults before use. If the version or checkpoint is invalid, keep the stored value available long enough to offer a safe new-game route instead of silently destroying it.

### Check

- Continue, new game, corrupt data, old version, and unknown checkpoint paths work.
- Checkpoints are stable Pages, not the middle of a Timer sequence.
- A failed save attempt does not clear the previous value first.
- Reset clears both persistent and in-memory state.

Load `../../implementation.md` when exact storage, JavaScript, navigation, Timer, audio, or Notification behavior matters.
