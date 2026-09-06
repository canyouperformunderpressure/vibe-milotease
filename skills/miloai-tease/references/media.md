# Media authoring

Use this reference only when images or audio materially affect the work. Media is authored inside Outline and Milo IR; it is not a separate main stage.

## Core rule

An image provides visible facts. Text selects, interprets, or extends those facts.

Text may add character voice, context, rules, off-screen player actions, consequences, or transitions that are not visible. It should not claim that the image shows a person, object, state, or action that contradicts what is actually present.

Inspect actual media before writing lines that depend on visible details. Filenames, gallery order, prompts, and prose ideas are not evidence of image contents.

## Decide the role of an image set

### Ordered sequence

Use when image order shows a visible progression: the same subject changes pose or clothing, an action advances, framing changes, or a situation reaches a result.

Write from useful differences between adjacent images while preserving continuity that the images themselves preserve. Text may bridge omitted time or off-screen events, but must remain compatible with the current visible frame.

### Themed pool

Use for independent Lottery or random-encounter material. Different subjects, locations, and styles may coexist when each item independently supports the same broad theme.

Do not invent continuity between randomly selected images. A pool result may be one image with a short matching line or a complete multi-image vignette.

### Repeated backdrop

One image may remain visible across several lines, rules, instructions, or choices. The text can advance without pretending the image changes.

### Thematic progression

Different subjects or visual styles can support one progressing challenge when continuity belongs to theme, action, pace, or intensity rather than identity.

## Outline handoff

During Outline creation, ask once how the user wants images handled. They may:

- provide images, galleries, folders, or links and associate them with parts of the work;
- describe desired characters, styles, settings, actions, or themes;
- explicitly delegate visual decisions;
- provide no visual direction.

Images are optional and their absence does not block Outline creation.

Record useful media intent naturally in node `content`. A node may mention one file, a folder/group, several possible vignettes, or only a visual requirement. Do not commit a group to linear, random, Lottery, or another runtime selection mechanism unless that structure has actually been decided.

Before candidate media becomes part of the work, show what was found and its intended use so the user can accept, reject, or redirect it. If visual selection was explicitly delegated, choose and report the result at the current stage handoff.

## Existing media

When media already exists:

1. Inspect the useful candidates.
2. Decide whether each set is an ordered sequence, themed pool, repeated backdrop, or thematic progression.
3. Keep images that establish, develop, distinguish, or resolve something useful; duplicates and gaps are acceptable when they serve the writing.
4. Make a semantic pass before implementation: ordered transitions fit visible changes, independent pool items stand alone, and text that describes the current frame remains true.

One coherent group can become a short vignette. A node may contain several vignettes.

## Sourcing media

When a node needs images that have not been selected, separate visible requirements from facts that text can provide. Search for the subject, setting, pose, action, object, or visual change the player actually needs to see; do not require one source image to encode all story context.

A scene can use different sets for different jobs, for example:

```text
location establishing image
→ character introduction
→ coherent action set
→ result or departure
```

Use Milo workflow media commands for supported sources:

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py media-search --provider pornpics --query "<visible theme>" --limit 20 --json
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py media-search --provider erome --query "<visible theme>" --limit 20 --json
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py media-fetch --project-id <numeric-id> --source-id <asset-id> --url "<selected-url>" --json
```

PornPics and EroMe accept direct queries. ImageFap requires locating a supported folder, gallery, image, or profile URL first. Search returns candidates without committing them to the work; fetch only plausible selected sources. Acquired author media stays under the selected project's `media/sources/` directory with provenance.

Use `--cookies <cookies.txt>` only when an authorized source requires an authenticated session.

Use only authorized material and do not bypass access restrictions.

## Image generation

Generate when an important visible requirement cannot be sourced, when an original character or location is required, or when a useful sequence lacks a specific transition.

For continuity-sensitive sequences:

1. Separate fixed facts from per-image changes.
2. Establish one useful anchor image for character, setting, and style.
3. Reuse that accepted anchor while changing only the visible details needed by the next frame.
4. Inspect the resulting images before writing final scene text.

When only one transition is missing, edit or extend the nearest suitable image instead of regenerating the whole sequence. Themed random pools do not require cross-image identity continuity unless the design explicitly asks for it.

Prefer sourcing ordinary material and generating only anchors, missing transitions, or special compositions where generation adds real value.

## Adult media

When adult media is part of the work, use material whose participants are clearly adults. Do not infer age from appearance alone. When visible anatomy, nudity, pose, sexual action, contact, or focal point matters to the writing, inspect what is actually present closely enough to avoid contradiction and leave uncertain details uncertain.

The same rule applies to generation: participants must be unambiguously adult, and prompts for required explicit visual states should specify the visible action or composition precisely enough to support the intended scene. Generated output must still be inspected before final prose treats any detail as visible fact.

## Project and Milo IR handoff

Keep acquired author files inside the selected project's `media/` tree. Outline references preserve authoring intent; they do not create runtime commands.

Declare reusable sources in `milo.yaml.assets`, then use executable image or audio actions in `src/*.milo.yaml`. Keep filenames and source grouping understandable when order or semantic grouping matters.

When a media path changes, keep matching Outline references and Milo IR asset references current.
