# MiloAIEditor

MiloAIEditor is the local host for the Milovana EOS Editor, Preview runtime, Tease Graph, and Milo IR compiler.

## Start

```powershell
python -m pip install -r requirements.txt
.\start.ps1
```

Open `http://127.0.0.1:8001/eos/editor/teases`. The service binds to `127.0.0.1`; online publishing and rating are disabled. `start.ps1 -Port <port>` or `milo_workflow.py --base-url` select a different port; the workflow tool always starts the service on the port embedded in `--base-url`.

## Project modes

- `milo-ir`: `outline.yaml` and the complete EOSScript YAML in `milo.yaml` plus `src/*.milo.yaml` are the editable sources. Optional shorthand reduces repeated command and resource syntax. Public EOS save APIs expose `eosscript.json` as generated, read-only output.
- `legacy-eos`: `eosscript.json` is editable through the EOS Editor. A project without `sourceMode` uses this mode.

A `milo-ir` project uses this structure:

```text
projects/<id>/
├─ project.json
├─ outline.yaml
├─ milo.yaml
├─ src/*.milo.yaml
├─ eosscript.json
├─ history/
├─ media/
└─ storage/state.json
```

## Workflow

Run workflow commands from the repository root. The workflow helper belongs to
the MiloAI tease skill, while the editor itself lives in `milo-editor/`:

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py new --title "Example" --project-id 100001 --json
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py build --project-id 100001 --json
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py build --project-id 100001 --open
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py migrate --project-id 39504 --json
```

Omit `--project-id` on `new` to allocate the next numeric ID. `new` preserves every project already present.

`POST /api/projects/<id>/build` accepts an empty body or `{}`. The build reads project sources, validates them, compiles deterministic EOS, materializes referenced media, validates the result, and atomically replaces `eosscript.json`. A failed build preserves the last successful script and Preview.

Migration imports every EOS top-level field and Page into Milo sources, rebuilds them, and switches the project mode only when the parsed JSON result is deeply equivalent to the original script.

For a `milo-ir` project, GraphQL and REST EOS save attempts return `GENERATED_ARTIFACT_READ_ONLY`. The EOS Editor can inspect, debug, and Preview the generated result. Compiler output is written through the internal generated-script path.

## Deploy to Milovana

The local EOS Editor injects a **Deploy to Milovana** button for project pages. You can deploy into an existing numeric tease ID or create a new EOS tease first. New-tease creation uses Milovana's `CreateTease(title, type: EOS)` mutation only after the user explicitly checks the same three responsibility/18+ acknowledgements required by the official Create page. The returned tease ID then feeds directly into the normal deploy pipeline.

Deployment uses the built `eosscript.json` and its materialized `media/timg` / `media/files` assets. It validates the complete backup with `validateEosScript`, saves that validated script first so a long transfer never leaves a blank tease, then checks each SHA-1, reuses existing hashes, and uploads missing media through the top-level browser form path. Each successful media operation is also persisted in the project's local `.milovana-deploy/<teaseId>.json` checkpoint. Retrying the same project/tease skips checkpointed media immediately instead of querying and re-attaching them from item 1 again; only new or unfinished media continue through the remote hash/upload path.

Deploy now runs through a dedicated, user-visible Chrome/Edge profile stored under the ignored `temp/milovana-browser` directory. Click **Open Milovana Browser** and log in normally. Playwright connects to the browser over local CDP, while Milovana GraphQL calls use the real `milovana.com` session. Media uploads use a dedicated real Chrome tab and a normal top-level `multipart/form-data` POST to `/api/eos/upload.php`; this avoids Cloudflare background-fetch challenges that may return `Just a moment...` HTML without ever showing a verification page in the editor tab. If Cloudflare does challenge the top-level upload tab, that tab is brought to the front so the normal browser challenge can run. Cookies and Cloudflare clearance are not exported to the Python backend.

The old `milo-test.json` cookie transport is no longer required by the normal Deploy flow. Deploy endpoints still reject non-local clients.

## Documentation

Read [SKILL.md](../skills/miloai-tease/SKILL.md),
[authoring.md](../skills/miloai-tease/references/authoring.md), and
[implementation.md](../skills/miloai-tease/references/implementation.md).
