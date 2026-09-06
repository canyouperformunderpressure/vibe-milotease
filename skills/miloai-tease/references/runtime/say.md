# Say rendering patterns

Use this focused reference for rich-text Say output that behaves like a small text renderer, especially static image sprites built from Unicode half-block characters. Read `../implementation.md` first for the normal Say contract.

Timing still follows the normal Say contract: `mode: autoplay` uses Runtime-estimated reading time and does not honor an authored `duration` as an exact wait. For a deliberate fixed display time, use `mode: custom` with `duration`. Do not use `autoplay + duration` to express exact timing.

## Rich-text rules used by the renderer

Say `label` can contain EOS rich-text HTML and inline `<eval>expression</eval>`. For dense sprite output:

The normal Say alignment contract still applies: use the command-level EOS `align: left|center|right` field to align the Say bubble. Any `text-align` inside the HTML produced by this renderer affects only the renderer's internal rich-text layout and must not be treated as a replacement for Say `align`.

- use explicit `<br>` row breaks; YAML source newlines are not a reliable visual row primitive;
- use a monospace font;
- set `letter-spacing:0`;
- use an explicit small `font-size` and `line-height`;
- keep the sprite in one `<p>` and color contiguous runs with `<span style="color:...">`;
- return the finished HTML string from a helper and insert it through `<eval>`.

## Reusable static half-block image sprite

The half-block method represents two sampled image rows with one text row. Each output character is one of:

```text
█  both sampled pixels use the same selected color
▀  selected color is on the top sample
▄  selected color is on the bottom sample
```

This doubles vertical sample density compared with one full-block character per sampled row while retaining simple, widely available Unicode block glyphs.

The shared preprocessor is:

```powershell
python skills/miloai-tease/tools/image_to_half_block/image_to_half_block.py <image> --columns 64 --colors 7
```

It performs this pipeline before runtime:

```text
image
-> corner-background estimate
-> foreground auto-crop with margin
-> aspect-preserving resize to N columns and an even pixel height
-> 2..16-color quantization
-> pair top/bottom pixels into █ / ▀ / ▄
-> merge adjacent same-color glyphs into runs
-> compact palette + row data
```

The tool prints JSON shaped like:

```json
{
  "columns": 64,
  "rows": 63,
  "palette": ["#ffffff", "#111111", "#f3baba"],
  "data": "0████~1▀▀~2▄▄|0████..."
}
```

Here `64×63` means 64 text columns by 63 half-block text rows. The source sampling grid is effectively 64×126 pixels because every text row contains a top and bottom sample.

The compact data format is intentionally simple:

- rows are separated by `|`;
- color runs inside a row are separated by `~`;
- the first character of each run is one hexadecimal palette index (`0..f`);
- the rest of the run is literal `█`, `▀`, or `▄` glyph data.

The one-hex-digit run prefix is why the shared converter limits the palette to 16 colors.

## Runtime helper

Store precomputed sprites and this renderer in `milo.yaml` `init`:

```yaml
init: |
  var STATIC_HALF_BLOCKS = {
    hero: {
      palette: ['#ffffff', '#111111', '#f3baba'],
      data: '0████~1▀▀~2▄▄|0████...'
    }
  };

  function renderStaticHalfBlock(name, fontSize, lineHeight) {
    var source = STATIC_HALF_BLOCKS[name];
    if (!source) return '';
    var rows = source.data.split('|');
    var htmlRows = [];
    for (var y = 0; y < rows.length; y++) {
      var encodedRuns = rows[y].split('~');
      var parts = [];
      for (var r = 0; r < encodedRuns.length; r++) {
        var encoded = encodedRuns[r];
        if (!encoded) continue;
        var paletteIndex = parseInt(encoded.charAt(0), 16);
        var text = encoded.substr(1);
        var color = source.palette[paletteIndex] || source.palette[0];
        parts.push('<span style="color:' + color + '">' + text + '</span>');
      }
      htmlRows.push(parts.join(''));
    }
    return '<p style="font-family:monospace;font-size:' + fontSize
      + 'px;line-height:' + lineHeight
      + ';letter-spacing:0;margin:0;text-align:center">'
      + htmlRows.join('<br>') + '</p>';
  }
```

Render it from a normal Say:

```yaml
- say:
    label: >-
      <b>Static image sprite</b><br>
      <eval>renderStaticHalfBlock('hero',3,0.58)</eval>
    mode: pause
```

The tested `64×63` variant used a 3px monospace display with `line-height:0.58`. A denser `80×79` variant used 2px with `line-height:0.55`. Treat those as known-good reference points for the tested environment, not universal browser limits; verify the actual target in Preview.

## Reference case: project 100004

Project `100004` is the reference case for **Auto image sprite · Static half-block** in Say. The useful tested forms are:

```text
64×63 text cells -> 3px font -> line-height 0.58 -> 7-color palette
80×79 text cells -> 2px font -> line-height 0.55 -> 11-color palette
```

The `64×63` form is the safer default when the visual must remain recognizable. The `80×79` form trades legibility and font-rendering margin for more detail.

This technique is not limited to ordinary pictures. It can be used for any small precomputed visual that benefits from Say's rich-text surface, including diagrams, silhouettes, symbols, maps, meters, decorative separators, puzzle clues, stylized UI fragments, or other special graphics.

The reference call is deliberately small:

```yaml
- say:
    label: >-
      <eval>renderStaticHalfBlock('hero',3,0.58)</eval>
    align: center
    mode: pause
```

For the denser form:

```yaml
- say:
    label: >-
      <eval>renderStaticHalfBlock('hero80',2,0.55)</eval>
    align: center
    mode: pause
```

The source image is precomputed with `tools/image_to_half_block/image_to_half_block.py`; runtime code only decodes compact palette/run data into rich-text spans. Do not embed thousands of generated spans directly into the scene file when the compact data form can be stored in `milo.yaml`.

This is a **static visual** case. Do not treat repeated Say commands as a smooth video surface: Say bubbles have lifecycle/fade/queue behavior and can produce visible transitions or ghosting. Use `runtime/video.md` for stock-EOS video-like playback and `runtime/notification.md` for low-resolution mutable Unicode animation.

## Color behavior

The converter's palette index `0` is the corner-estimated background color. When both sampled pixels quantize to the same palette entry, the renderer emits `█` in that color. This means the sprite carries an explicit background-colored cell instead of depending on CSS `background-color` for empty areas.

When top and bottom samples are different and one is background, `▀` or `▄` preserves the foreground half. When both are different non-background colors, a single half-block cell cannot show both colors independently with foreground-only CSS. The converter keeps the sample with greater contrast from the detected background. The representation is therefore deliberately lossy.

If that tradeoff is unacceptable, use a renderer with foreground and background CSS per cell or a denser Unicode encoding; do not silently claim the half-block form is lossless.

## When to use this method

Use precomputed static half-block Say sprites when:

- the image is intentionally tiny/pixel-like;
- no runtime image decoding is needed;
- compact authored source is preferable to thousands of inline spans;
- a static Say bubble is acceptable.

Do not treat Say as a general canvas. Repeated Say commands create/replace bubble UI according to Page flow rather than mutating one text node like `Notification.setTitle`. For frame animation, choose the runtime surface deliberately and test bubble lifecycle/fade behavior in Preview.

## Practical checks

- Keep palette size between 2 and 16 for the compact one-digit run format.
- Precompute outside EOS runtime; do not perform Pillow/image processing in `init`.
- Keep generated data as inert strings in `milo.yaml`.
- Use `<eval>` only to return the renderer's HTML string; the helper itself should not navigate Pages.
- Preview small fonts on the actual host. Font fallback, minimum-size behavior, antialiasing, and display scaling can change alignment.
- If the source background is not reasonably represented by its corners, override or adapt the preprocessing step rather than trusting auto-crop blindly.

