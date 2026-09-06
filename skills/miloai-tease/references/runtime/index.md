# Runtime pattern index

Use this index only when implementation needs a specialized rendering or playback technique beyond the normal EOS contracts in `../implementation.md`.

This file is a router, not an implementation reference. Read only the focused case that matches the requested surface.

| Need | Load | Use when |
| --- | --- | --- |
| Dense rich-text Say output or static Unicode image/special visual | [`say.md`](say.md) | Small static images, symbols, diagrams, maps, meters, puzzle clues, decorative UI fragments, or other visuals that benefit from Say rich text. |
| Mutable low-resolution Unicode/Braille animation in persistent UI | [`notification.md`](notification.md) | A compact animation, HUD, indicator, or stroke/motion display can live inside one persistent Notification and update through `Notification.get(id).setTitle(...)`. |
| Video-like motion without changing the EOS runtime | [`video.md`](video.md) | Photographic or many-frame motion should use native `image` commands paced by hidden Timers, optionally with background audio. |

## Selection rules

- Prefer normal EOS `image` for ordinary static media. Do not convert a normal picture to Unicode merely because the technique exists.
- Prefer [`say.md`](say.md) when the visual must appear inside the Say surface or when a tiny precomputed graphic is intentionally part of the text presentation.
- Prefer [`notification.md`](notification.md) when the content must mutate in place. Notification is lower-resolution and less styleable than Say, but its title can be updated without creating a new Say bubble.
- Prefer [`video.md`](video.md) for sustained multi-frame visual motion. Repeated Say commands are not a smooth video surface because bubble lifecycle, fade, and queue behavior remain visible.
- Do not load all three cases by default. Load this index, choose the relevant case, then read only that file unless the design deliberately combines surfaces.

## Known reference cases

- `say.md` — project `100004`, **Auto image sprite · Static half-block**, including tested `64×63 @ 3px` and `80×79 @ 2px` forms.
- `notification.md` — project `100009`, persistent Braille frame animation with hidden-Timer clock, title mutation, ping-pong phase, and compact frame patches.
- `video.md` — reusable stock-EOS image-sequence playback method based on `tools/video_to_eos/video_to_eos.py`; reusable documentation excludes private source video and private frames.

These projects are reference cases, not dependencies. Reuse the method and code pattern; keep project-specific visual payloads in the project that owns them.
