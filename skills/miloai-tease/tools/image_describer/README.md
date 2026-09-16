# Batch Image Description Tool

`describe_images.py` scans an image directory and sends one Cherry Studio API request per image.

Each request uses this context order:

1. Optional user-supplied system prompt, only when `--system-prompt <file>` is provided
2. Bootstrap user message requesting a detailed image description
3. Bootstrap assistant acknowledgement
4. The image-description task followed by exactly one image

This project does not bundle or provide jailbreak/safety-bypass prompts. By default, the image describer sends no system prompt. The tool uses Cherry Studio's Anthropic-compatible `/v1/messages` endpoint and model `new-api:gemini-3.1-pro-preview`.

## Requirements

- Python 3.10+
- Cherry Studio API running at `http://127.0.0.1:23333`
- No additional Python packages are required

## PowerShell usage

Open PowerShell at the repository root. Read the API key into an environment variable for the current process:

```powershell
$secureKey = Read-Host "Cherry API key" -AsSecureString
$env:CHERRY_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
```

Describe all images in a directory:

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py "D:\path\to\images"
```

Use multiple workers while keeping the combined request rate at five HTTP requests per minute:

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py "D:\path\to\images" --concurrency 4 --requests-per-minute 5
```

Scan subdirectories recursively:

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py "D:\path\to\images" --recursive
```

Preview the files that would be processed without calling the API:

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py "D:\path\to\images" --recursive --dry-run
```

Choose an output directory:

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py "D:\path\to\images" -o "D:\path\to\results"
```

Provide a custom description task:

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py "D:\path\to\images" --task "Describe the people, environment, clothing, expressions, and actions in the image in detail."
```

You can also use `--task-file D:\path\to\task.txt` to load the task from a UTF-8 text file.

To use your own system prompt, provide it explicitly:

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py "D:\path\to\images" --system-prompt "D:\path\to\my-prompt.md"
```

## Output and repeat runs

The default output directory is `<input directory>\descriptions`:

```text
images/
├─ first.jpg
├─ sub/second.png
└─ descriptions/
   ├─ first.jpg.md
   ├─ sub/second.png.md
   └─ _manifest.json
```

- Each image receives a matching `.md` description file.
- `_manifest.json` records completed, skipped, and failed files.
- Existing descriptions are skipped by default to avoid duplicate API usage.
- Use `--overwrite` to regenerate existing descriptions.
- One failed image does not stop the rest of the batch; network errors and rate limits are retried automatically.
- The default global limit is five requests per minute, shared by all workers and retries.
- `--include-dir <relative-directory>` may be repeated to process selected subdirectories only.

Show all options:

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py --help
```
