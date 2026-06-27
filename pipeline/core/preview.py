"""Vite preview server lifecycle.

Deterministic tooling (no LLM): serves the built ``dist/`` on a free port so
Playwright can capture the rendered page.
"""

from __future__ import annotations

import socket
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class PreviewServer:
    """A running ``vite preview`` process and the URL it serves."""

    process: subprocess.Popen
    url: str

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()


def start_preview(workdir: Path, *, ready_timeout: float = 60.0) -> PreviewServer:
    """Start ``vite preview`` on a free port and wait until it serves.

    Requires a prior successful production build (preview serves ``dist/``).
    Binds explicitly to 127.0.0.1 so it works the same in a container.
    """
    host = "127.0.0.1"
    port = _free_port()
    proc = subprocess.Popen(
        [
            "npm",
            "run",
            "preview",
            "--",
            "--host",
            host,
            "--port",
            str(port),
            "--strictPort",
        ],
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://{host}:{port}/"
    _wait_until_serving(url, proc, ready_timeout)
    return PreviewServer(process=proc, url=url)


def _wait_until_serving(url: str, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            out = _drain(proc)
            raise RuntimeError(
                "Preview server exited before becoming ready.\n" + out
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.4)
    out = _drain(proc)
    raise TimeoutError(
        f"Preview server did not become ready within {timeout}s.\n" + out
    )


def _drain(proc: subprocess.Popen) -> str:
    """Best-effort capture of the server's output for diagnostics."""
    try:
        proc.terminate()
        out, _ = proc.communicate(timeout=5)
        return (out or "").strip()[-2000:]
    except Exception:  # noqa: BLE001
        return "(no server output captured)"
