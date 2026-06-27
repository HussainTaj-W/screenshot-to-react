"""Toolchain preflight.

Verifies the CLI tools and runtimes each stage needs before any stage runs.
Safe (npm-based) tools are auto-installed when missing; system-level tools
(e.g. Node.js) fail loudly with an actionable message rather than attempting a
privileged install.

See spec ``pipeline-orchestration`` → "Verify and provision the toolchain
before stages run".
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

# Minimum Node.js major version (Netlify CLI requires Node 18.14+).
MIN_NODE_MAJOR = 18


class PreflightError(Exception):
    """Raised when a required system-level tool is missing or too old.

    This deliberately does NOT cover auto-installable tools — those are
    provisioned silently.
    """


@dataclass
class PreflightResult:
    """Outcome of a preflight run."""

    installed: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def did_install(self) -> bool:
        return bool(self.installed)


def _which(tool: str) -> str | None:
    return shutil.which(tool)


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _node_major_version() -> int | None:
    """Return the installed Node.js major version, or None if absent/unparseable."""
    if _which("node") is None:
        return None
    proc = _run(["node", "--version"], timeout=30)
    if proc.returncode != 0:
        return None
    # e.g. "v23.7.0"
    raw = proc.stdout.strip().lstrip("v")
    try:
        return int(raw.split(".", 1)[0])
    except (ValueError, IndexError):
        return None


def check_node(min_major: int = MIN_NODE_MAJOR) -> None:
    """Fail loudly if Node.js is missing or below the minimum version.

    Node is system-level: we never attempt a privileged install.
    """
    major = _node_major_version()
    if major is None:
        raise PreflightError(
            "Node.js is required but was not found on PATH.\n"
            "Install Node.js (>= "
            f"{min_major}.14) from https://nodejs.org/ or via your package "
            "manager (e.g. `brew install node`), then re-run."
        )
    if major < min_major:
        raise PreflightError(
            f"Node.js {min_major}.14+ is required, but found major version "
            f"{major}.\nUpgrade Node.js and re-run."
        )


def ensure_playwright_browsers() -> bool:
    """Ensure the Playwright Chromium browser is installed.

    Returns True if an install was performed, False if already present.
    Safe to auto-install (downloads into the user cache, no privileges).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dependency guaranteed by uv
        raise PreflightError(
            "The 'playwright' Python package is not installed. Run `uv add playwright`."
        ) from exc

    # Probe: can we launch chromium headless?
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return False
    except Exception:
        # Browser binary likely missing — install it.
        proc = _run(["playwright", "install", "chromium"])
        if proc.returncode != 0:
            # Fall back to invoking via the module if the console script is absent.
            proc = _run(["python", "-m", "playwright", "install", "chromium"])
        if proc.returncode != 0:
            raise PreflightError(
                f"Failed to install the Playwright Chromium browser.\nstderr: {proc.stderr.strip()}"
            ) from None
        return True


def ensure_netlify_cli() -> bool:
    """Ensure the Netlify CLI is reachable.

    Returns True if an install was performed, False if already present.
    The CLI is npm-based and safe to auto-install. We prefer a global-free
    approach: if `netlify` is not on PATH, install it locally via npm so it can
    be invoked with `npx netlify`.
    """
    if _which("netlify") is not None:
        return False

    # Is it resolvable through npx without a fresh install? Check a local
    # node_modules first; otherwise install locally.
    npm = _which("npm")
    if npm is None:
        # Node present (checked separately) but npm missing is unusual.
        raise PreflightError(
            "npm is required to provision the Netlify CLI but was not found.\n"
            "Ensure your Node.js installation includes npm."
        )
    proc = _run([npm, "install", "netlify-cli", "--no-save", "--no-audit", "--no-fund"])
    if proc.returncode != 0:
        raise PreflightError(
            f"Failed to install the Netlify CLI via npm.\nstderr: {proc.stderr.strip()}"
        )
    return True


def run_preflight(
    *,
    require_netlify: bool = True,
    min_node_major: int = MIN_NODE_MAJOR,
) -> PreflightResult:
    """Run the full toolchain preflight.

    Order:
      1. Node.js / npm  (system-level → fail loud if missing/old)
      2. Playwright browsers (safe → auto-install)
      3. Netlify CLI (safe → auto-install), unless ``require_netlify`` is False.

    Passes through without installing anything when already satisfied.
    """
    result = PreflightResult()

    # 1. Node.js (system-level, never auto-install).
    check_node(min_node_major)
    result.already_present.append("node")

    if _which("npm") is None:
        raise PreflightError("npm was not found on PATH. Ensure your Node.js install includes npm.")
    result.already_present.append("npm")

    # 2. Playwright browsers (safe to auto-install).
    if ensure_playwright_browsers():
        result.installed.append("playwright-chromium")
    else:
        result.already_present.append("playwright-chromium")

    # 3. Netlify CLI (safe to auto-install).
    if require_netlify:
        if ensure_netlify_cli():
            result.installed.append("netlify-cli")
        else:
            result.already_present.append("netlify-cli")
    else:
        result.notes.append("Skipped Netlify CLI check (deploy disabled).")

    return result
