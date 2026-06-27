"""Vite + React + Tailwind project scaffolding.

Deterministic tooling (no LLM): writes the base project files so the builder
coding agent only has to fill ``src/`` with the actual page, and copies extracted
assets into ``public/`` so the build bundles them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def is_scaffolded(workdir: Path) -> bool:
    """Whether ``workdir`` already contains a scaffolded project."""
    return (workdir / "package.json").is_file() and (workdir / "src").is_dir()


def scaffold_app(workdir: Path) -> None:
    """Create a minimal Vite + React + Tailwind v4 project in ``workdir``.

    Writes files directly (rather than ``npm create vite``) for determinism and
    speed; the builder agent fills ``src/App.jsx`` and ``src/index.css`` with the
    actual page. ``npm install`` is run separately to populate node_modules.
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
        '<!doctype html>\n<html lang="en">\n  <head>\n'
        '    <meta charset="UTF-8" />\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        "    <title>Landing</title>\n  </head>\n  <body>\n"
        '    <div id="root"></div>\n'
        '    <script type="module" src="/src/main.jsx"></script>\n'
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
        (workdir / "src" / "index.css").write_text('@import "tailwindcss";\n')
    if not (workdir / "src" / "App.jsx").exists():
        (workdir / "src" / "App.jsx").write_text(
            "export default function App() {\n"
            '  return <main className="min-h-screen" />\n}\n'
        )


def copy_extracted_assets(assets_dir: Path, workdir: Path) -> list[str]:
    """Copy extracted asset files from requirements/assets into ``public/``.

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
