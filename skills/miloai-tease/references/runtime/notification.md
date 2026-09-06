# Notification patterns

Use this focused reference when a Notification needs behavior beyond one static card, especially persistent title updates, frame animation, or same-ID replacement. Read `../implementation.md` first for the canonical Notification and Timer contracts.

## Runtime surface

Create and remove cards with canonical EOS commands:

```yaml
- notification.create:
    id: status
    title: Ready

- notification.remove:
    id: status
```

After a card with an explicit ID exists, JavaScript can address it with:

```javascript
var notice = Notification.get('status');
if (notice) {
  notice.setTitle('Running');
  notice.remove();
}
```

The runtime-exposed Notification object supports `setTitle(string)` and `remove()`. Do not assume setters for the button or native timer. If button or timer configuration must change, create the Notification again with the same ID; same-ID creation replaces the old card.

## Hard runtime constraint: EOS `eval` is not the browser event loop

EOS `init` and `eval.script` execute inside the host's JavaScript interpreter VM, not directly in the browser `window` context. Only globals explicitly exposed by the EOS host may be used. The browser host itself may use APIs such as `setTimeout` or `setInterval` internally; that does **not** make those functions available to authored EOS JavaScript.

For Milo/EOS authoring, treat browser timer APIs as unavailable unless the target EOS host explicitly exposes and documents them. In particular, do **not** build gameplay, Notification animation, polling, delayed transitions, or repeated work around `setInterval`, `clearInterval`, `setTimeout`, or `clearTimeout` from `init`/`eval`.

This failure can look deceptively harmless: the EOS `eval` command catches JavaScript exceptions and logs them, so a missing timer global can leave the Page running while the intended animation silently never starts. A static Notification with no frame updates is a typical symptom.

**Hard rule:** repeated or wall-clock-driven behavior must be scheduled by EOS commands. For title animation, use a persistent Notification plus a synchronous `timer` with `style: hidden`, then `goto` a dedicated loop Page. The loop Page calls the frame-step helper once per tick. A button or other stop route must `goto` a Page outside that loop.

The Page Granularity Principle does not prohibit this structure. A dedicated hidden Timer loop is a genuine runtime loop target and is therefore an intentional Page boundary. Do not collapse such a loop into a long foreground Timer plus a browser `setInterval` merely to reduce Page count.

When an animation only needs approximate visual motion, a Timer-driven loop may advance state one step per tick. **Do not use tick count as the timebase when wall-clock accuracy or audio synchronization matters.** A nominal `16.67ms` EOS Timer loop also pays Page navigation, `eval`, condition, and rendering overhead, so the loop will not execute at an exact 60 Hz. Fixed `phase += rate / 60` logic therefore runs slow and drifts.

For synchronized animation, separate the two clocks:

- **EOS Timer = sampling/scheduling clock.** It decides when the next frame can be rendered.
- **`Date.now()` = animation phase clock.** It decides which frame should be visible now and whether a fixed-duration phase has ended.

This makes dropped or delayed EOS ticks reduce visual smoothness without changing the intended motion speed.

## Audio and metronome synchronization

When a Notification animation follows an audio metronome, define the relationship explicitly. If one complete `0 -> last -> 0` animation cycle represents one beat, then:

```javascript
cyclesPerSecond = bpm / 60;
phase = ((Date.now() - startedAtMs) / 1000 * cyclesPerSecond) % 1;
```

For a metronome file whose first click is at audio time `0`, use frame `0` as the beat anchor. Start the audio and immediately capture `startedAtMs`; each later metronome click should then correspond to phase `0` again. Examples:

- 60 BPM -> `1.0` complete animation cycle per second;
- 90 BPM -> `1.5` cycles per second;
- 140 BPM -> `140 / 60 = 2.333333...` cycles per second, not `2.3`.

Do not put a blocking `say`, foreground Timer, Choice, or other queue pause between `audio.play` and the animation-loop start. A four-second Say after `audio.play`, for example, makes a zero-offset metronome begin four seconds before the first animated frame. If dialogue must be presented before synchronized motion, show the dialogue first, then start the audio and animation together.

For a fixed synchronized phase such as 35 seconds, store an absolute end time (`startedAtMs + 35000`) and test `Date.now()` against it. Do not assume `2100` EOS loop iterations equal exactly 35 seconds.

## Reusable persistent title animation

For text, Unicode-art, Braille, block-character, or other title frames, keep one Notification alive and mutate only its title. Recreating the card for every frame causes unnecessary component replacement and can make the animation visibly flash or re-enter.

Use a hidden EOS Timer as the sampling clock. Do not depend on browser `setInterval` being available inside the EOS JavaScript VM.

Put the reusable controller in `milo.yaml` `init`:

```yaml
modules:
  notification: {}

init: |
  function createNotificationTitleAnimation(id, frames, cyclesPerSecond, tickHz) {
    var hz = Number(tickHz) || 60;
    if (!(hz > 0)) hz = 60;
    var rate = Number(cyclesPerSecond) || 1;
    if (!(rate > 0)) rate = 1;
    return {
      id: String(id),
      frames: frames || [],
      rate: rate,
      tickHz: hz,
      tickMs: 1000 / hz,
      startedAtMs: Date.now()
    };
  }

  function setNotificationTitleAnimationRate(animation, cyclesPerSecond) {
    var rate = Number(cyclesPerSecond);
    if (!(rate > 0)) rate = 1;
    animation.rate = rate;
    animation.startedAtMs = Date.now();
    return rate;
  }

  function resetNotificationTitleAnimation(animation) {
    animation.startedAtMs = Date.now();
  }

  function notificationTitleAnimationFrame(animation, index) {
    if (!animation || !animation.frames || !animation.frames.length) return '';
    var count = animation.frames.length;
    var i = Math.floor(Number(index) || 0);
    i = ((i % count) + count) % count;
    return String(animation.frames[i]);
  }

  function stepNotificationTitleAnimation(animation) {
    if (!animation || !animation.frames || !animation.frames.length) return -1;

    var elapsedMs = Date.now() - animation.startedAtMs;
    if (elapsedMs < 0) elapsedMs = 0;
    var phase = ((elapsedMs / 1000) * animation.rate) % 1;

    // One complete cycle is 0 -> last -> 0.
    var travel = phase < 0.5
      ? phase * 2
      : (1 - phase) * 2;
    var frame = Math.round(travel * (animation.frames.length - 1));
    if (frame < 0) frame = 0;
    if (frame >= animation.frames.length) frame = animation.frames.length - 1;

    var notice = Notification.get(animation.id);
    if (notice) notice.setTitle(String(animation.frames[frame]));
    return frame;
  }
```

Define only the ascending source frames. The controller supplies the return path automatically:

```javascript
var STROKE_FRAMES = [FRAME_0, FRAME_1, FRAME_2, FRAME_3];
var STROKE_ANIMATION = createNotificationTitleAnimation(
  'stroke-animation',
  STROKE_FRAMES,
  1,
  60
);
```

For an animation whose source frames are numbered `0..29`, one logical cycle is:

```text
0 -> 1 -> ... -> 28 -> 29 -> 28 -> ... -> 1 -> 0
```

`cyclesPerSecond` means complete ping-pong cycles per second. The hidden Timer only samples the current wall-clock phase. At high rates or under load it may skip source frames, but the cycle does not become slower merely because the EOS loop missed a nominal 60 Hz tick.

Drive the controller from Milo IR with one looping Page:

```yaml
pages:
  animation-start:
    - notification.create:
        id: stroke-animation
        title: Starting…
        buttonLabel: Stop animation
        buttonCommands:
          - goto:
              target: animation-controls
    - eval:
        script: >-
          setNotificationTitleAnimationRate(STROKE_ANIMATION, 1);
          Notification.get('stroke-animation').setTitle(notificationTitleAnimationFrame(STROKE_ANIMATION, 0));
    - goto:
        target: animation-loop

  animation-loop:
    - eval:
        script: stepNotificationTitleAnimation(STROKE_ANIMATION);
    - timer:
        duration: $STROKE_ANIMATION.tickMs
        style: hidden
    - goto:
        target: animation-loop
```

The stop button should route to a Page outside the loop. That button command interrupts the active animation flow; the destination Page can replace the same ID with an idle card or remove it.

## Why mutation and replacement are different

- Use `Notification.get(id).setTitle(...)` for frame-by-frame title changes. It keeps the same card/component alive.
- Use another `notification.create` with the same ID when button label/commands or native timer configuration must change. This replaces the card.
- Use `notification.remove` or `Notification.get(id).remove()` when the UI is finished.

Do not use same-ID replacement as the normal frame primitive for a title-only animation.

## Frame-data strategy

Large Unicode frames can make `milo.yaml` noisy. Keep the animation helper generic and choose one of these data layouts:

1. A direct array of full strings when the frame set is small.
2. One base frame plus incremental patches when consecutive frames differ only in a few character ranges.
3. A generated array produced in `init` from compact source data.

The animation controller only requires `frames[index]` to be a string. Frame encoding is independent from playback.

## Reference case: project 100009 Braille stroke animation

Project `100009` is the reference case for a low-resolution animated graphic inside one persistent Notification. Its important design is not the specific drawing; it is the combination of:

- Unicode Braille frames;
- one persistent Notification ID;
- `Notification.get(id).setTitle(...)` for frame mutation;
- a hidden 60 Hz EOS Timer loop;
- a triangle-wave phase so `0 -> last -> 0` is one logical stroke/cycle;
- base-frame + incremental patches so similar frames do not need to be stored as complete duplicate strings.

Project `100009` has two related Braille payloads that must not be conflated:

- `anim_loop` animates `DICK_STROKE_FRAMES`, built from `DICK_STROKE_FRAME0` plus `DICK_STROKE_PATCHES`. This is the shaft/head stroke shown in reference image 1 and intentionally does **not** include the scrotum.
- The scrotum-containing outline shown in reference image 2 is the separate static `DICK_STROKE_STOP` payload used on the controls/stopped state. It is not an animation source frame and must not be copied into `DICK_STROKE_FRAME0` or `DICK_STROKE_PATCHES`.
- When using project `100009` as a visual animation reference, inspect `/eos/editor/100009/preview` while execution is inside `anim_loop`; do not use the stopped/controls card as the target animation shape.

The compact frame builder used by that case has this shape:

```javascript
var DICK_STROKE_FRAME0 = '...Braille frame 0...';

var DICK_STROKE_PATCHES = [
  [[158, '...replacement...']],
  [[159, '...replacement...']],
  [[121, '...replacement...'], [163, '...replacement...']]
];

function buildDickStrokeFrames() {
  var frames = [DICK_STROKE_FRAME0];
  var chars = DICK_STROKE_FRAME0.split('');
  for (var i = 0; i < DICK_STROKE_PATCHES.length; i++) {
    var patches = DICK_STROKE_PATCHES[i];
    for (var j = 0; j < patches.length; j++) {
      var start = patches[j][0];
      var replacement = patches[j][1];
      for (var k = 0; k < replacement.length; k++) {
        chars[start + k] = replacement.charAt(k);
      }
    }
    frames.push(chars.join(''));
  }
  return frames;
}

var DICK_STROKE_FRAMES = buildDickStrokeFrames();
var DICK_STROKE_TICK_MS = 1000 / 60;
var DICK_STROKE_RATE = 1;
var DICK_STROKE_STARTED_AT_MS = Date.now();

function setDickStrokeRate(rate) {
  DICK_STROKE_RATE = Number(rate);
  if (!(DICK_STROKE_RATE > 0)) DICK_STROKE_RATE = 1;
  DICK_STROKE_STARTED_AT_MS = Date.now();
}

function advanceDickStroke() {
  var count = DICK_STROKE_FRAMES.length;
  var elapsedMs = Date.now() - DICK_STROKE_STARTED_AT_MS;
  if (elapsedMs < 0) elapsedMs = 0;
  var phase = ((elapsedMs / 1000) * DICK_STROKE_RATE) % 1;
  var travel = phase < 0.5
    ? phase * 2
    : (1 - phase) * 2;
  var frame = Math.round(travel * (count - 1));
  if (frame < 0) frame = 0;
  if (frame >= count) frame = count - 1;

  var notice = Notification.get('dick-braille');
  if (notice) notice.setTitle(DICK_STROKE_FRAMES[frame]);
  return frame;
}
```

The scene loop is:

```yaml
pages:
  animation-start:
    - notification.create:
        id: dick-braille
        title: Starting…
        buttonLabel: Stop animation
        buttonCommands:
          - goto:
              target: controls
    - eval:
        script: setDickStrokeRate(1);
    - goto:
        target: anim-loop

  anim-loop:
    - eval:
        script: advanceDickStroke();
    - timer:
        duration: $DICK_STROKE_TICK_MS
        style: hidden
    - goto:
        target: anim-loop
```

Keep the actual Braille frame payload project-specific. The reusable skill knowledge is the mutation clock, ping-pong phase, and compact patch encoding. For a different shape, generate different base/patch data instead of rewriting the controller.

## Practical checks

- Create the Notification before the first `Notification.get(id)` call.
- Keep every title frame a string; `setTitle` rejects non-string values.
- Give persistent cards a deliberate stop/remove path.
- Keep the frame loop hidden; a visible Timer would create unwanted UI for every tick.
- Test Unicode art in Preview. Notification width, fallback glyph metrics, antialiasing, and device scaling can change the appearance even when the string is identical.
- Treat the hidden Timer cadence as a sampling target, not the animation timebase. Runtime/render load may skip or delay rendered frames; wall-clock phase calculation should preserve the intended speed and audio relationship.

