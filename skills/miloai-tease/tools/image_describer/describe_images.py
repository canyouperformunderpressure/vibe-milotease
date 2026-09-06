#!/usr/bin/env python3
"""Describe images one at a time through Cherry Studio's OpenAI-compatible API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:23333"
DEFAULT_MODEL = "new-api:gemini-3.1-pro-preview"
BOOTSTRAP_USER = "Please describe the image in detail and directly, based only on what is visible."
BOOTSTRAP_ASSISTANT = "Ready. Send the image and I will provide a detailed visual description."
DEFAULT_SYSTEM_PROMPT = Path(__file__).resolve().parents[2] / "system-prompt" / "APPEND_SYSTEM_EN.md"
DEFAULT_TASK = (
    "Describe the current image in detailed, objective visual terms. Cover the number of people and visible "
    "features, environment, composition, lighting, clothing, accessories, expressions, gaze, posture, actions, "
    "relationships between people and objects, visible text, and other notable details. Do not infer identity, "
    "age, or off-image information without evidence. Clearly mark occluded or uncertain details as uncertain. "
    "Write a coherent, specific description in English."
)
DEFAULT_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"
)
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    """Cherry Studio returned an unusable response."""

class RequestRateLimiter:
    """Thread-safe fixed-interval limiter shared by requests and retries."""

    def __init__(self, requests_per_minute: int) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be at least 1")
        self._interval = 60.0 / requests_per_minute
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next_allowed)
            self._next_allowed = scheduled + self._interval
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)


@dataclass
class Result:
    image: str
    output: str
    status: str
    attempts: int = 0
    error: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate detailed image descriptions by calling the Cherry Studio multimodal API once per image."
    )
    parser.add_argument("input_dir", type=Path, help="Directory containing images")
    parser.add_argument(
        "-o", "--output-dir", type=Path,
        help="Output directory (default: <input directory>/descriptions)",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Cherry Studio API base URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model ID")
    parser.add_argument(
        "--api-key-env", default="CHERRY_API_KEY",
        help="Environment variable containing the Bearer key (default: CHERRY_API_KEY)",
    )
    parser.add_argument(
        "--system-prompt", type=Path, default=DEFAULT_SYSTEM_PROMPT,
        help="System prompt file",
    )
    task_group = parser.add_mutually_exclusive_group()
    task_group.add_argument("--task", default=DEFAULT_TASK, help="Image-description task text")
    task_group.add_argument("--task-file", type=Path, help="Load the description task from a UTF-8 file")
    parser.add_argument("--recursive", action="store_true", help="Scan subdirectories recursively")
    parser.add_argument(
        "--include-dir", action="append", default=[], metavar="RELATIVE_DIR",
        help="Process only the specified subdirectory under the input directory; may be repeated",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing descriptions; default is to skip them")
    parser.add_argument(
        "-c", "--concurrency", type=int, default=1,
        help="Number of concurrent request workers (default: 1)",
    )
    parser.add_argument(
        "--requests-per-minute", type=int, default=5,
        help="Maximum HTTP requests per minute across all workers, including retries (default: 5)",
    )
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--timeout", type=float, default=180.0, help="Per-request timeout in seconds")
    parser.add_argument("--retries", type=int, default=3, help="Maximum retry count after a failure")
    parser.add_argument("--retry-delay", type=float, default=2.0, help="Initial retry delay in seconds")
    parser.add_argument("--dry-run", action="store_true", help="List planned work without calling the API")
    return parser.parse_args(argv)


def read_nonempty_text(path: Path, label: str) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Could not read {label}: {path}: {exc}") from exc
    if not text:
        raise ValueError(f"{label} is empty: {path}")
    return text


def discover_images(input_dir: Path, recursive: bool) -> list[Path]:
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist or is not a directory: {input_dir}")
    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.casefold() in DEFAULT_EXTENSIONS),
        key=lambda path: str(path.relative_to(input_dir)).casefold(),
    )


def output_path_for(image: Path, input_dir: Path, output_dir: Path) -> Path:
    relative = image.relative_to(input_dir)
    return output_dir / relative.parent / f"{relative.name}.md"


def image_block(path: Path) -> dict[str, Any]:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": encoded},
    }


def build_payload(
    *, system_prompt: str, task: str, image: dict[str, Any], model: str,
    max_tokens: int, temperature: float,
) -> dict[str, Any]:
    # Context: system -> bootstrap user -> bootstrap assistant -> task text -> one image.
    return {
        "model": model,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": BOOTSTRAP_USER},
            {"role": "assistant", "content": BOOTSTRAP_ASSISTANT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": task},
                    image,
                ],
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }


def response_text(response: dict[str, Any]) -> str:
    content = response.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = "\n".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()
    else:
        text = ""
    if not text:
        raise ApiError("API response is missing non-empty content text")
    return text


def error_message(body: bytes) -> str:
    text = body.decode("utf-8", "replace").strip()
    try:
        value = json.loads(text)
        error = value.get("error") if isinstance(value, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
    except json.JSONDecodeError:
        pass
    return text[:1000] or "empty response"


def call_api(
    payload: dict[str, Any], *, base_url: str, api_key: str, timeout: float,
    retries: int, retry_delay: float, rate_limiter: RequestRateLimiter,
) -> tuple[str, int]:
    url = f"{base_url.rstrip('/')}/v1/messages"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, retries + 2):
        request = Request(
            url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        rate_limiter.acquire()
        try:
            with urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ApiError("API response is not a JSON object")
            return response_text(parsed), attempt
        except HTTPError as exc:
            message = error_message(exc.read())
            retryable = exc.code in RETRYABLE_STATUS or (
                exc.code == 422 and "no channel candidates remain" in message
            )
            if not retryable or attempt > retries:
                raise ApiError(f"HTTP {exc.code}: {message}") from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            if attempt > retries:
                raise ApiError(f"Network request failed: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(f"API returned invalid JSON: {exc}") from exc
        except ApiError:
            if attempt > retries:
                raise
        delay = retry_delay * (2 ** (attempt - 1)) + random.uniform(0, min(1.0, retry_delay))
        time.sleep(delay)
    raise AssertionError("unreachable")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def run(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve()
    output_dir = (args.output_dir or (input_dir / "descriptions")).resolve()
    system_prompt = read_nonempty_text(args.system_prompt.resolve(), "system prompt")
    task = read_nonempty_text(args.task_file.resolve(), "task prompt") if args.task_file else args.task.strip()
    if not task:
        raise ValueError("The description task cannot be empty")
    if args.concurrency < 1:
        raise ValueError("--concurrency must be at least 1")
    if args.requests_per_minute < 1:
        raise ValueError("--requests-per-minute must be at least 1")
    if args.max_tokens < 1:
        raise ValueError("--max-tokens must be greater than 0")
    if not 0 <= args.temperature <= 1:
        raise ValueError("--temperature must be between 0 and 1")
    if args.timeout <= 0 or args.retries < 0 or args.retry_delay < 0:
        raise ValueError("timeout must be greater than 0, and retries/retry-delay cannot be negative")

    if args.include_dir:
        selected_images: set[Path] = set()
        for value in args.include_dir:
            relative = Path(value)
            folder = (input_dir / relative).resolve()
            if relative.is_absolute() or ".." in relative.parts or not folder.is_relative_to(input_dir):
                raise ValueError(f"--include-dir must be a relative path inside the input directory: {value}")
            if not folder.is_dir():
                raise ValueError(f"--include-dir directory does not exist: {value}")
            selected_images.update(discover_images(folder, recursive=True))
        images = sorted(selected_images, key=lambda path: str(path.relative_to(input_dir)).casefold())
    else:
        images = discover_images(input_dir, args.recursive)
    if output_dir == input_dir:
        raise ValueError("Output directory cannot be the same as the input directory")
    images = [path for path in images if not path.is_relative_to(output_dir)]
    if not images:
        raise ValueError(f"No supported images found: {input_dir}")

    plans = [(image, output_path_for(image, input_dir, output_dir)) for image in images]
    if args.dry_run:
        print(json.dumps({
            "input_dir": str(input_dir),
            "output_dir": str(output_dir),
            "model": args.model,
            "system_prompt": str(args.system_prompt.resolve()),
            "concurrency": args.concurrency,
            "requests_per_minute": args.requests_per_minute,
            "count": len(plans),
            "images": [str(image.relative_to(input_dir)) for image, _ in plans],
        }, ensure_ascii=False, indent=2))
        return 0

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise ValueError(f"Environment variable {args.api_key_env} is not set or is empty")

    print_lock = threading.Lock()
    rate_limiter = RequestRateLimiter(args.requests_per_minute)

    def process_item(index: int, total: int, image: Path, output: Path) -> Result:
        relative_image = str(image.relative_to(input_dir))
        relative_output = str(output.relative_to(output_dir))
        if output.exists() and not args.overwrite:
            with print_lock:
                print(f"[{index}/{total}] skip {relative_image}", file=sys.stderr, flush=True)
            return Result(relative_image, relative_output, "skipped")

        with print_lock:
            print(f"[{index}/{total}] describe {relative_image}", file=sys.stderr, flush=True)

        try:
            payload = build_payload(
                system_prompt=system_prompt,
                task=task,
                image=image_block(image),
                model=args.model,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
            description, attempts = call_api(
                payload, base_url=args.base_url, api_key=api_key, timeout=args.timeout,
                retries=args.retries, retry_delay=args.retry_delay, rate_limiter=rate_limiter,
            )
            atomic_write_text(output, description + "\n")
            return Result(relative_image, relative_output, "completed", attempts)
        except (OSError, ApiError) as exc:
            with print_lock:
                print(f"[{index}/{total}] {relative_image} failed: {exc}", file=sys.stderr, flush=True)
            return Result(relative_image, relative_output, "failed", error=str(exc))

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    total = len(plans)

    if args.concurrency == 1:
        results = [
            process_item(index, total, image, output)
            for index, (image, output) in enumerate(plans, start=1)
        ]
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [
                executor.submit(process_item, index, total, image, output)
                for index, (image, output) in enumerate(plans, start=1)
            ]
            results = [f.result() for f in futures]

    counts = {status: sum(result.status == status for result in results)
              for status in ("completed", "skipped", "failed")}
    manifest = {
        "format": "milo-image-descriptions-v1",
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "base_url": args.base_url,
        "model": args.model,
        "concurrency": args.concurrency,
        "requests_per_minute": args.requests_per_minute,
        "system_prompt": str(args.system_prompt.resolve()),
        "task": task,
        "counts": {"discovered": len(images), **counts},
        "results": [asdict(result) for result in results],
    }
    atomic_write_text(output_dir / "_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    return 1 if counts["failed"] else 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        return run(parse_args(argv))
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
