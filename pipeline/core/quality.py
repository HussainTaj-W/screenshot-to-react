"""Advisory quality gate: lint + accessibility (axe).

This is ADVISORY ONLY (design.md decision 3 / user clarification): it records
findings but never blocks or loops. Findings are surfaced in the gaps report.
Build success is the hard contract; quality checks are "extra steps".
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def run_quality_checks(workdir: Path) -> list[str]:
    """Run advisory checks and return a list of human-readable findings.

    Never raises for lint/a11y failures — findings are informational. If the
    tools are not present, that itself is recorded as a (soft) note rather than
    failing the pipeline.
    """
    findings: list[str] = []

    # ESLint (best-effort; many scaffolds won't have a config — that's fine).
    try:
        proc = _run(["npx", "--no-install", "eslint", "src", "--format", "compact"], workdir)
        if proc.returncode != 0 and proc.stdout.strip():
            findings.append("ESLint findings:\n" + proc.stdout.strip())
        elif proc.returncode != 0 and proc.stderr.strip():
            findings.append("ESLint not run: " + proc.stderr.strip().splitlines()[-1])
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        findings.append(f"ESLint skipped: {exc}")

    # axe accessibility is run against the rendered page in the capture step via
    # @axe-core/playwright when available; here we only note intent so the gaps
    # report can include a11y. A dedicated runtime hook can populate this.
    return findings


def run_axe(url: str) -> list[str]:
    """Run axe-core against a live URL via Playwright, returning violations.

    Advisory: returns a list of finding strings; returns an empty list (with a
    note) if axe-core is unavailable, never raising.
    """
    findings: list[str] = []
    try:
        from axe_playwright_python.sync_playwright import Axe  # type: ignore
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ["axe a11y check skipped: axe-playwright-python not installed."]

    try:  # pragma: no cover - exercised only when axe is installed
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            results = Axe().run(page)
            for v in results.response.get("violations", []):
                findings.append(f"a11y [{v.get('impact')}]: {v.get('help')}")
            browser.close()
    except Exception as exc:  # pragma: no cover
        findings.append(f"axe a11y check error: {exc}")
    return findings
