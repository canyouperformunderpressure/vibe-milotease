# Edge, Cum & Permission Rules

## Design profile

- **Role:** Modifier / cross-phase rule pattern
- **Best for:** control, denial, permission, consequence, risk
- **Typical scale:** scene / cross-phase
- **Can lead a phase:** Usually no
- **Player mainly:** report or react to edge/cum states under explicit permission rules
- **Combines well with:** `metronome-stroking.md`, `edge-hold-loop.md`, `surrender-option.md`, `progression.md`


This pattern models player-reported Edge / Cum events and explicit permission rules. It should expose neutral event outcomes that the current project can interpret, rather than embedding one story's punishment, corruption, or ending logic.

## Core Concepts

1. **Floating Action Overlays**: Using `notification.create` with `buttonLabel` and `buttonCommands` for persistent `EDGE` and `CUM` triggers during stroking or dialog.
2. **Event State**: Track counts or timestamps only when later gameplay needs them.
3. **Permission Model**: A reported Cum event resolves to a small neutral result such as `authorized`, `violation`, or `continue-with-consequence`.
4. **Composition Boundary**: Willpower, sensitivity, punishment, content toggles, progression, and endings belong to their own patterns or project rules unless this mechanic explicitly composes with them.

---

## Reusable JavaScript Engine (`milo.yaml.init`)

```javascript
// Edge / Cum event state
var edgeCount = 0;
var cumCount = 0;
var lastEdgeTime = 0;
var permissionGranted = false;
var continueAfterViolation = false;

// Register an Edge event
function handleEdgeEvent() {
  edgeCount++;
  lastEdgeTime = Date.now();
  updateEventHUD();
  return "edge-reported";
}

// Register a Cum event
function handleCumEvent() {
  cumCount++;
  updateEventHUD();
  if (permissionGranted) return "authorized";
  return continueAfterViolation ? "continue-with-consequence" : "violation";
}

function updateEventHUD() {
  var hud = Notification.get("hud-status");
  if (hud) {
    hud.setTitle("Edges: " + edgeCount + " | Cum: " + cumCount);
  }
}
```

---

## Milo IR Patterns

### Persistent Floating Edge & Cum Buttons

```yaml
pages:
  interactive-stroking-hub:
    - notification:
        id: hud-status
        title: "Edges: 0 | Cum: 0"
    - notification:
        id: btn-edge
        buttonLabel: "Reached EDGE (Edge!)"
        buttonCommands:
          - eval:
              script: |
                handleEdgeEvent();
                pages.goto("edge-recovery");
    - notification:
        id: btn-cum
        buttonLabel: "Accidental orgasm (CUM)"
        buttonCommands:
          - eval:
              script: |
                var result = handleCumEvent();
                if (result === "violation") {
                  pages.goto("permission-violation");
                } else if (result === "continue-with-consequence") {
                  pages.goto("permission-consequence");
                } else {
                  pages.goto("authorized-cum");
                }
```

### Cleanup on Node Exit

```yaml
pages:
  clear-action-buttons:
    - eval:
        script: |
          var b1 = Notification.get("btn-edge"); if (b1) b1.remove();
          var b2 = Notification.get("btn-cum"); if (b2) b2.remove();
          var hud = Notification.get("hud-status"); if (hud) hud.remove();
```

The destination Pages above are intentionally semantic rather than story-specific. The project decides whether a violation retries, branches, changes progression, applies another mechanic, or ends the sequence.

## Check

- Permission is explicit before a Cum event can resolve as authorized.
- Event buttons are removed when leaving the interaction scope.
- A violation route is defined without assuming a particular punishment or ending.
- Counts/timestamps are tracked only when another rule actually consumes them.
- Project-specific character types, lore, endings, and content-taxonomy rules stay outside this pattern.
