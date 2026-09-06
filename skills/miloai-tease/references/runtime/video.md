# Stock-EOS video-like playback

Use this focused reference when a tease needs to reproduce video-like motion **without modifying the EOS runtime**. This case intentionally contains no source video, private frame content, or hard-coded source path. It documents only the conversion and playback method.

The repository already includes the reusable converter:

```powershell
python skills/miloai-tease/tools/video_to_eos/video_to_eos.py "<private-video>" `
  --projects-root projects `
  --project-id <numeric-id> `
  --fps 24 `
  --frames-per-page 24
```

Do not copy the private source video into this reference. The source path is supplied only when the user runs the tool locally.

## Why this uses Image instead of Say

Stock EOS does not expose a mutable Say label API. Repeated Say frames create bubble lifecycle/fade/queue effects, so a half-block Say sprite is a good **static** image/special-visual technique but not a reliable smooth video surface.

The native `image` command uses the media area and replaces the current displayed image. Therefore the stock-EOS video approximation is:

```text
private video
-> FFmpeg frame extraction
-> optional audio extraction
-> package JPEG frames as an EOS gallery
-> image frame
-> hidden Timer
-> next image frame
-> hidden Timer
-> ...
```

No engine modification is required.

## Conversion

The existing tool uses FFmpeg to extract a fixed-rate JPEG sequence and optional MP3 audio. The essential conversion command is equivalent to:

```python
command = [
    ffmpeg,
    '-hide_banner',
    '-nostdin',
    '-i', str(video),
    '-map', '0:v:0',
    '-vf', 'fps=24',
    '-q:v', '2',
    '-start_number', '1',
    str(media_dir / 'frame_%06d.jpg'),
    '-map', '0:a:0?',
    '-vn',
    '-codec:a', 'libmp3lame',
    '-q:a', '2',
    str(media_dir / 'video_audio.mp3'),
]
```

Tune FPS, JPEG quality, resolution before extraction, and duration according to storage and fidelity needs. Stock EOS image playback has no inter-frame video compression, so frame count and JPEG size directly affect storage.

## Gallery packaging

Each generated frame is packaged as an EOS gallery image and addressed by a stable locator:

```python
def frame_locator(gallery_id: str, frame_id: int) -> str:
    return f'gallery:{gallery_id}/{frame_id}'
```

The converter hashes/copies each frame into the project's local media tree and records width, height, size, hash, and numeric ID in the gallery metadata.

Do not put the original source path into authored runtime logic. The generated project needs only packaged media metadata and frame locators.

## Playback page generator

EOS preloads a Page's media. Very long single Pages can create a large preload burst, so chunk the sequence into small playback Pages. The bundled tool defaults to 24 frames per Page.

Reusable core logic:

```python
def build_playback_pages(frames, locate, fps=24, frames_per_page=24):
    pages = {}

    for chunk_start in range(0, len(frames), frames_per_page):
        page_number = chunk_start // frames_per_page + 1
        page_name = f'playback_{page_number:06d}'
        chunk = frames[chunk_start:chunk_start + frames_per_page]
        commands = []

        for chunk_index, frame in enumerate(chunk):
            frame_index = chunk_start + chunk_index + 1
            commands.append({
                'image': {'locator': locate(frame)}
            })

            # 24 FPS = 41.666... ms. EOS literal durations are integer ms,
            # so 42, 42, 41 averages exactly 41.666... ms.
            if fps == 24:
                duration_ms = 41 if frame_index % 3 == 0 else 42
            else:
                duration_ms = max(1, round(1000 / fps))

            timer = {
                'duration': f'{duration_ms}ms',
                'style': 'hidden',
            }

            if chunk_index == len(chunk) - 1:
                if frame_index == len(frames):
                    target = 'finished'
                else:
                    target = f'playback_{page_number + 1:06d}'
                timer['commands'] = [
                    {'goto': {'target': target}}
                ]

            commands.append({'timer': timer})

        pages[page_name] = commands

    return pages
```

For non-24-FPS playback, a single rounded duration is simple but may accumulate drift. For precise rates, generate a repeating integer-millisecond pattern whose average equals `1000 / fps`.

## Optional audio

If the source has audio, start it once on the first playback Page as background audio:

```json
{
  "audio.play": {
    "locator": "file:video_audio.mp3",
    "volume": 1,
    "loops": 1,
    "background": true,
    "id": "video_audio"
  }
}
```

Then let image/timer playback continue across Page chunks. Background audio avoids restarting at every Page boundary.

## Canonical EOS shape

A minimal generated playback Page looks like:

```yaml
playback-000001:
  - image:
      locator: gallery:<gallery-id>/<frame-1-id>
  - timer:
      duration: 42ms
      style: hidden
  - image:
      locator: gallery:<gallery-id>/<frame-2-id>
  - timer:
      duration: 42ms
      style: hidden
  - image:
      locator: gallery:<gallery-id>/<frame-3-id>
  - timer:
      duration: 41ms
      style: hidden
      commands:
        - goto:
            target: playback-000002
```

The last Timer in each chunk owns the cross-Page Goto. Intermediate Timers simply pace the next image command on the same Page.

## Privacy and source handling

- Keep this reference free of the source video and extracted frames.
- Do not hard-code a private source filename or absolute source path into reusable docs.
- The generated frame files themselves still contain the video's visual content. Treat the generated project/media directory according to the user's privacy requirements.
- If only the technique needs to be preserved, keep the converter and this reference; do not preserve a private demonstration project's media.

## Storage tradeoffs

Because stock EOS displays independent JPEG images, it cannot use normal MP4/WebM inter-frame compression. Reduce storage by choosing among:

- lower frame resolution;
- lower JPEG quality;
- lower FPS;
- shorter converted duration;
- duplicate/similar-frame reuse when appropriate;
- adaptive frame sampling for low-motion sections.

Do not claim this is native video playback. It is a timed EOS image sequence designed to reproduce video-like motion within the stock runtime.

## When to use which rendering case

- **Say static half-block:** small high-detail static image, diagram, symbol, or special visual -> `say.md`.
- **Notification Braille animation:** low-resolution mutable Unicode animation/HUD -> `notification.md`.
- **Image sequence:** video-like motion or many photographic frames -> this file.
