# Release Audit

Release target: `miloai-tease-editor-release-en-20260906-ready`

## Scope

This bundle contains the Vibe MiloTease skill and the MiloAIEditor runtime needed for local authoring, Tease Graph editing, preview, validation, compilation, media workflows, and deployment support.

Excluded from the public bundle: local projects and project contents, browser profiles, authentication/session state, credentials, logs, captures, test suites, test artifacts, pytest temporary directories, Python caches, npm caches, `node_modules`, and other local development state.

An empty `projects/` directory is included only as a workspace placeholder.

## License

Original Vibe MiloTease project code is distributed under the MIT License in `LICENSE`. Bundled or vendored third-party components retain their own upstream licenses and redistribution terms; see `THIRD_PARTY_NOTICES.md`.

## English release

Public-facing project documentation, workflow CLI output, editor integration text, API/validation errors, Tease Graph UI, Outline templates, examples, and image-description defaults were translated to English.

Intentional non-English text remains only where it serves compatibility or optional reference purposes:

- `skills/miloai-tease/references/writing-guide-zh.md` is an explicitly optional Chinese writing guide.
- `milo-editor/app/milo_ir/migration.py` retains four Chinese failure keywords solely to recognize legacy Chinese projects during migration.
- Bundled third-party parser/runtime assets may contain CJK Unicode tables or character data; these are not user-interface strings.

## Validation

- Tease Graph unit tests: 39 passed, 0 failed.
- Tease Graph production build completed successfully and generated `milo-editor/tease-graph/dist/standalone.html`.
- Python syntax compilation completed successfully for `milo-editor/app` and `skills/miloai-tease/tools`.
- `image_describer --help` and `milo_workflow --help` both completed successfully with English output.
- MiloAIEditor import/health smoke test returned `ok: true`, `editorAssets: true`, and `runtimeAvailable: true`.
- Public `start.ps1` binds the editor to `127.0.0.1`.

## Information-leak scan

Final staging scan found no matches for the checked categories: common OpenAI/GitHub/Slack/AWS/Google API-key formats, private-key headers, embedded username/password URLs, workspace-specific absolute paths, Windows user-profile paths, or the previously observed local username.

This is a targeted release-hygiene scan, not a legal or security certification.
