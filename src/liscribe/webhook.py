"""Webhook delivery helpers.

Two entry points:
  send_transcript — multipart/form-data POST with the .md file + metadata fields.
  send_dictation  — JSON POST with raw dictated text + metadata.

Both are fire-and-forget (log on failure, never raise).
Auth header is injected when both auth_header_name and auth_header_value are non-empty.
"""

from __future__ import annotations

import io
import json
import logging
import mimetypes
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_auth_headers(name: str, value: str) -> dict[str, str]:
    if name and value:
        return {name: value}
    return {}


def _encode_multipart(fields: dict[str, str], file_name: str, file_data: bytes) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Returns (body_bytes, content_type_header)."""
    boundary = "LiscribeWebhookBoundary7c3b1a"
    lines: list[bytes] = []

    for key, val in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{key}"'.encode())
        lines.append(b"")
        lines.append(val.encode("utf-8"))

    lines.append(f"--{boundary}".encode())
    mime_type = mimetypes.guess_type(file_name)[0] or "text/markdown"
    lines.append(
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"'.encode()
    )
    lines.append(f"Content-Type: {mime_type}".encode())
    lines.append(b"")
    lines.append(file_data)

    lines.append(f"--{boundary}--".encode())

    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_transcript(
    url: str,
    md_path: str | Path,
    *,
    source: str = "scribe",
    word_count: int = 0,
    duration_seconds: float = 0.0,
    model: str = "",
    auth_header_name: str = "",
    auth_header_value: str = "",
) -> None:
    """POST the .md file as multipart/form-data to *url*.

    Fields sent alongside the file:
      source          — "scribe" or "transcribe"
      created_at      — ISO-8601 timestamp
      word_count      — integer word count
      duration_seconds — float, rounded to 1 decimal
      model           — whisper model name used
    """
    md_path = Path(md_path)
    try:
        file_data = md_path.read_bytes()
    except OSError as exc:
        logger.warning("Webhook: could not read %s: %s", md_path, exc)
        return

    fields = {
        "source": source,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "word_count": str(word_count),
        "duration_seconds": str(round(duration_seconds, 1)),
        "model": model,
    }

    body, content_type = _encode_multipart(fields, md_path.name, file_data)

    headers: dict[str, str] = {"Content-Type": content_type}
    headers.update(_build_auth_headers(auth_header_name, auth_header_value))

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            pass
        logger.info("Webhook: transcript sent to %s (%s)", url, md_path.name)
    except Exception as exc:
        logger.warning("Webhook: POST to %r failed: %s", url, exc)


def send_dictation(
    url: str,
    text: str,
    *,
    duration_seconds: float = 0.0,
    auth_header_name: str = "",
    auth_header_value: str = "",
) -> None:
    """POST dictated text as JSON to *url*.

    Body fields:
      workflow        — always "dictate"
      text            — the transcribed/dictated text
      timestamp       — ISO-8601
      word_count      — integer
      duration_seconds — float rounded to 1 decimal
    """
    payload = {
        "source": "dictate",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "word_count": len(text.split()),
        "duration_seconds": round(duration_seconds, 1),
        "text": text,
    }

    data = json.dumps(payload, separators=(",", ":")).encode()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    headers.update(_build_auth_headers(auth_header_name, auth_header_value))

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
        logger.info("Webhook: dictation sent to %s", url)
    except Exception as exc:
        logger.warning("Webhook: dictation POST to %r failed: %s", url, exc)
