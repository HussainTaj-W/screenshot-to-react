"""Outgoing LLM request capture for debugging provider errors (e.g. HTTP 400).

When enabled (``PIPELINE_DEBUG_REQUESTS=1``), patches ``httpx.AsyncClient.send``
to dump each outgoing model request body to a JSONL file, with image/base64 data
summarized (length only) instead of inlined. This lets us inspect exactly what
was sent on a failing request without flooding the log with megabytes of base64.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

_PATCHED = False

# Where to write captured requests.
DEFAULT_DUMP_PATH = Path("debug_requests.jsonl")


def _summarize(obj: Any) -> Any:
    """Recursively replace long base64/data-URI strings with a summary."""
    if isinstance(obj, str):
        if len(obj) > 500 and ("base64," in obj or obj[:20].isalnum()):
            return f"<str len={len(obj)} head={obj[:32]!r}>"
        return obj
    if isinstance(obj, dict):
        return {k: _summarize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_summarize(v) for v in obj]
    return obj


def enable(dump_path: Path | str = DEFAULT_DUMP_PATH) -> None:
    """Patch httpx to dump outgoing model request bodies (idempotent)."""
    global _PATCHED
    if _PATCHED:
        return

    import httpx

    path = Path(dump_path)
    orig_send = httpx.AsyncClient.send

    async def send(self, request, **kwargs):  # type: ignore[no-untyped-def]
        url = str(request.url)
        if "/responses" in url or "/chat/completions" in url:
            record: dict[str, Any] = {"url": url}
            try:
                record["body"] = _summarize(json.loads(request.content.decode()))
            except Exception as exc:  # noqa: BLE001
                record["body_error"] = str(exc)
            try:
                response = await orig_send(self, request, **kwargs)
            except Exception as exc:  # noqa: BLE001
                record["exception"] = repr(exc)
                _append(path, record)
                raise
            record["status"] = response.status_code
            if response.status_code >= 400:
                # Read the error body so we can correlate request <-> error.
                with contextlib.suppress(Exception):
                    record["error_body"] = (await response.aread()).decode()[:1000]
            _append(path, record)
            return response
        return await orig_send(self, request, **kwargs)

    httpx.AsyncClient.send = send  # type: ignore[method-assign]
    _PATCHED = True


def _append(path: Path, record: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def enable_if_configured() -> None:
    """Enable capture when ``PIPELINE_DEBUG_REQUESTS`` is truthy."""
    val = os.environ.get("PIPELINE_DEBUG_REQUESTS", "").strip().lower()
    if val in {"1", "true", "yes"}:
        dump = os.environ.get("PIPELINE_DEBUG_REQUESTS_PATH") or DEFAULT_DUMP_PATH
        enable(dump)
