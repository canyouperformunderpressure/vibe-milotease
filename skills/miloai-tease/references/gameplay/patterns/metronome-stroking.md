# Metronome & Stroking Pacing System

## Design profile

- **Role:** Anchor or modifier pattern
- **Best for:** rhythm, pacing, escalating intensity, embodied attention
- **Typical scale:** scene / phase
- **Can lead a phase:** Yes
- **Player mainly:** follow a changing beat, stroke count, grip, area, or cadence rule
- **Combines well with:** `timed-challenge.md`, `dual-task-challenge.md`, `edge-hold-loop.md`, `surrender-option.md`


This system handles audio-synchronized cadence, procedural stroke counting, and dynamic BPM modulation.

## Core Concepts

1. **Audio Metronomes**: Audio assets looped via `audio.play` with explicit playback IDs (e.g. `metronomeTrack`), stopped on completion or user interrupt.
2. **Pace Multipliers**: Pacing factors (e.g. 0.33x Quick to 2.0x Marathon) that scale required stroke counts and timer durations.
3. **Dynamic Stroke Formula**: Computing duration $T = \frac{60}{\text{BPM}} \times \text{Strokes} \times \text{Multiplier}$.
4. **Floating BPM Controls**: Allowing real-time tempo shifts using `notification.create` and JavaScript state.

---

## Reusable JavaScript Engine (`milo.yaml.init`)

```javascript
// Pacing & Metronome Runtime State
var bpmSpeed = 90; // Default BPM
var paceMultiplier = 1.0; // 0.66 (Easy), 1.0 (Normal), 1.5 (Hard)
var totalStrokesRecorded = 0;
var strokeRoundActive = false;

var bpmTable = {
  1: 45,
  2: 60,
  3: 90,
  4: 120,
  5: 150,
  6: 180
};

// Calculate task duration in milliseconds
function calculateStrokeDuration(strokes, bpm) {
  var effectiveBpm = bpm || bpmSpeed;
  return Math.round((60 / effectiveBpm) * strokes * paceMultiplier * 1000);
}

// Generate procedural stroke instruction
function generateStrokeInstruction(baseStrokes, style) {
  var strokes = Math.round(baseStrokes * paceMultiplier);
  var targetAreas = [
    "the full length with a normal grip",
    "only the cock head with two fingers",
    "the entire shaft with a firm, tight grip",
    "the base and shaft with gentle, teasing strokes"
  ];
  var area = targetAreas[Math.floor(Math.random() * targetAreas.length)];
  return {
    strokes: strokes,
    text: "Follow the metronome: Stroke " + area + " for " + strokes + " beats!"
  };
}

function stopMetronome(trackId) {
  var id = trackId || "metronomeTrack";
  var sound = Sound.get(id);
  if (sound) sound.stop();
}
```

---

## Milo IR Patterns

### 1. Fixed BPM Timed Stroke Page

```yaml
# Assets declaration in milo.yaml
assets:
  metro-90bpm: media/sources/audio/90-bpm.mp3

# Scene page implementation
pages:
  stroking-beat-90:
    - eval:
        script: strokeRoundActive = true;
    - audio:
        asset: metro-90bpm
        action: play
        id: metronomeTrack
        loops: 0 # Loop indefinitely until stopped
    - say:
        label: "<p>Stroke firmly in time with each beat. Do not stop until the timer ends!</p>"
    - timer:
        duration: 30s
        style: normal
        isAsync: true
        commands:
          - if:
              condition: strokeRoundActive === true
              commands:
                - eval:
                    script: |
                      strokeRoundActive = false;
                      stopMetronome("metronomeTrack");
                - goto:
                    target: stroke-rest
    - choice:
        options:
          - label: "Reached Edge!"
            commands:
              - eval:
                  script: |
                    strokeRoundActive = false;
                    stopMetronome("metronomeTrack");
              - goto:
                  target: edge-handler
```

### 2. Dynamic BPM Adjuster with Floating Notification

```yaml
pages:
  dynamic-metronome-page:
    - notification:
        id: btn-faster
        buttonLabel: "Increase Speed (+)"
        buttonCommands:
          - eval:
              script: |
                bpmSpeed = Math.min(180, bpmSpeed + 30);
                Notification.get("hud-bpm").setTitle("BPM: " + bpmSpeed);
    - notification:
        id: btn-slower
        buttonLabel: "Decrease Speed (-)"
        buttonCommands:
          - eval:
              script: |
                bpmSpeed = Math.max(45, bpmSpeed - 30);
                Notification.get("hud-bpm").setTitle("BPM: " + bpmSpeed);
    - notification:
        id: hud-bpm
        title: "BPM: 90"
```
