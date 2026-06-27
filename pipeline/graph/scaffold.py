"""Vite + React + Tailwind scaffolding, build, and preview operations.

Deterministic tooling (no LLM): scaffolds the app, runs the production build
(the build-success contract), and serves a preview for Playwright capture.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BuildResult:
    succeeded: bool
    stdout: str
    stderr: str

    @property
    def error_summary(self) -> str:
        # Keep the tail of stderr/stdout — compile errors live at the end.
        tail = (self.stderr or self.stdout or "").strip().splitlines()[-40:]
        return "\n".join(tail)


def _run(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def is_scaffolded(workdir: Path) -> bool:
    return (workdir / "package.json").is_file() and (workdir / "src").is_dir()


def scaffold_app(workdir: Path) -> None:
    """Create a minimal Vite + React + Tailwind v4 project in ``workdir``.

    Writes files directly (rather than ``npm create vite``) for determinism and
    speed; the builder agent fills ``src/App.jsx`` and ``src/index.css`` with the
    actual page. ``npm install`` is run to populate node_modules.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "src").mkdir(exist_ok=True)
    (workdir / "public").mkdir(exist_ok=True)

    (workdir / "package.json").write_text(
        json.dumps(
            {
                "name": workdir.name,
                "private": True,
                "version": "0.0.0",
                "type": "module",
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {
                    "react": "^18.3.1",
                    "react-dom": "^18.3.1",
                    "lucide-react": "^0.460.0",
                    # ^ icon library; broad range so npm resolves a working build.
                },
                "devDependencies": {
                    "@vitejs/plugin-react": "^4.3.4",
                    "vite": "^6.0.0",
                    "tailwindcss": "^4.0.0",
                    "@tailwindcss/vite": "^4.0.0",
                },
            },
            indent=2,
        )
    )

    (workdir / "vite.config.js").write_text(
        "import { defineConfig } from 'vite'\n"
        "import react from '@vitejs/plugin-react'\n"
        "import tailwindcss from '@tailwindcss/vite'\n\n"
        "export default defineConfig({ plugins: [react(), tailwindcss()] })\n"
    )

    (workdir / "index.html").write_text(
        "<!doctype html>\n<html lang=\"en\">\n  <head>\n"
        "    <meta charset=\"UTF-8\" />\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
        "    <title>Landing</title>\n  </head>\n  <body>\n"
        "    <div id=\"root\"></div>\n"
        "    <script type=\"module\" src=\"/src/main.jsx\"></script>\n"
        "  </body>\n</html>\n"
    )

    (workdir / "src" / "main.jsx").write_text(
        "import { StrictMode } from 'react'\n"
        "import { createRoot } from 'react-dom/client'\n"
        "import './index.css'\n"
        "import App from './App.jsx'\n\n"
        "createRoot(document.getElementById('root')).render(\n"
        "  <StrictMode>\n    <App />\n  </StrictMode>,\n)\n"
    )

    # Placeholder content; the builder agent overwrites these.
    if not (workdir / "src" / "index.css").exists():
        (workdir / "src" / "index.css").write_text("@import \"tailwindcss\";\n")
    if not (workdir / "src" / "App.jsx").exists():
        (workdir / "src" / "App.jsx").write_text(
            "export default function App() {\n"
            "  return <main className=\"min-h-screen\" />\n}\n"
        )


def npm_install(workdir: Path, timeout: int = 900) -> BuildResult:
    proc = _run(["npm", "install", "--no-audit", "--no-fund"], workdir, timeout)
    return BuildResult(proc.returncode == 0, proc.stdout, proc.stderr)


def build_app(workdir: Path, timeout: int = 600) -> BuildResult:
    """Run the production build — the build-success contract gate."""
    proc = _run(["npm", "run", "build"], workdir, timeout)
    return BuildResult(proc.returncode == 0, proc.stdout, proc.stderr)


def copy_extracted_assets(assets_dir: Path, workdir: Path) -> list[str]:
    """Copy extracted asset files from requirements/assets into public/.

    Returns the list of filenames copied. The canonical copy stays in
    requirements/assets (source of record); these are build inputs.
    """
    public = workdir / "public"
    public.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if not assets_dir.is_dir():
        return copied
    for f in assets_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, public / f.name)
            copied.append(f.name)
    return copied


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class PreviewServer:
    process: subprocess.Popen
    url: str

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()


def start_preview(workdir: Path, *, ready_timeout: float = 30.0) -> PreviewServer:
    """Start ``vite preview`` on a free port and wait until it serves.

    Requires a prior successful ``build_app`` (preview serves ``dist/``).
    """
    port = _free_port()
    proc = subprocess.Popen(
        ["npm", "run", "preview", "--", "--port", str(port), "--strictPort"],
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{port}/"
    _wait_until_serving(url, proc, ready_timeout)
    return PreviewServer(process=proc, url=url)


def _wait_until_serving(url: str, proc: subprocess.Popen, timeout: float) -> None:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Preview server exited before becoming ready.")
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.4)
    raise TimeoutError(f"Preview server did not become ready within {timeout}s.")
