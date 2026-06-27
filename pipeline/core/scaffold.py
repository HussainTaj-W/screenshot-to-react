"""Vite + React + Tailwind project scaffolding.

Deterministic tooling (no LLM): scaffolds a base project with the official
``npm create vite`` CLI, then layers Tailwind v4 and lucide-react on top, so the
builder coding agent only has to fill ``src/`` with the actual page. Extracted
assets are copied into ``public/`` so the build bundles them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# Versions layered on top of the create-vite base.
_TAILWIND_VERSION = "^4.0.0"
_TAILWIND_VITE_PLUGIN_VERSION = "^4.0.0"
_LUCIDE_VERSION = "^0.460.0"


class ScaffoldError(RuntimeError):
    """Raised when the base project cannot be scaffolded."""


def is_scaffolded(workdir: Path) -> bool:
    """Whether ``workdir`` already contains a scaffolded project."""
    return (workdir / "package.json").is_file() and (workdir / "src").is_dir()


def scaffold_app(workdir: Path) -> None:
    """Scaffold a Vite + React + Tailwind v4 project in ``workdir``.

    Uses the official ``npm create vite`` CLI for the React base, then adds
    Tailwind v4 (+ its Vite plugin) and lucide-react. The builder agent fills
    ``src/App.jsx`` and ``src/index.css`` with the actual page. ``npm install``
    is run separately to populate node_modules.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    _create_vite_base(workdir)
    _add_tailwind_and_icons(workdir)
    _reset_entry_files(workdir)
    (workdir / "public").mkdir(exist_ok=True)


def _create_vite_base(workdir: Path) -> None:
    """Run ``npm create vite`` non-interactively to scaffold the React base.

    create-vite refuses to scaffold into a non-empty directory, so we run it in
    a temporary sibling and move the contents in.
    """
    parent = workdir.parent
    tmp_name = f".{workdir.name}__vite_scaffold"
    tmp_dir = parent / tmp_name
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    proc = subprocess.run(
        ["npm", "create", "vite@latest", tmp_name, "--", "--template", "react"],
        cwd=parent,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if proc.returncode != 0 or not (tmp_dir / "package.json").is_file():
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ScaffoldError(
            "npm create vite failed:\n" + (proc.stderr or proc.stdout).strip()
        )

    # Move scaffolded contents into workdir, then drop the temp dir.
    for item in tmp_dir.iterdir():
        dest = workdir / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(item), str(dest))
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _add_tailwind_and_icons(workdir: Path) -> None:
    """Add Tailwind v4 (+ Vite plugin) and lucide-react to the create-vite base."""
    pkg_path = workdir / "package.json"
    pkg = json.loads(pkg_path.read_text())

    pkg.setdefault("name", workdir.name)
    pkg.setdefault("dependencies", {})["lucide-react"] = _LUCIDE_VERSION
    dev = pkg.setdefault("devDependencies", {})
    dev["tailwindcss"] = _TAILWIND_VERSION
    dev["@tailwindcss/vite"] = _TAILWIND_VITE_PLUGIN_VERSION
    pkg_path.write_text(json.dumps(pkg, indent=2) + "\n")

    # Register the Tailwind Vite plugin alongside the React plugin.
    (workdir / "vite.config.js").write_text(
        "import { defineConfig } from 'vite'\n"
        "import react from '@vitejs/plugin-react'\n"
        "import tailwindcss from '@tailwindcss/vite'\n\n"
        "// https://vite.dev/config/\n"
        "export default defineConfig({\n"
        "  plugins: [react(), tailwindcss()],\n"
        "})\n"
    )


def _reset_entry_files(workdir: Path) -> None:
    """Replace create-vite's demo CSS/App with our minimal placeholders.

    main.jsx from create-vite already imports './index.css' and './App.jsx', so
    only those two need resetting. Drop the demo App.css if present.
    """
    src = workdir / "src"
    src.mkdir(exist_ok=True)

    (src / "index.css").write_text('@import "tailwindcss";\n')
    (src / "App.jsx").write_text(
        "export default function App() {\n"
        '  return <main className="min-h-screen" />\n}\n'
    )
    app_css = src / "App.css"
    if app_css.exists():
        app_css.unlink()


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
