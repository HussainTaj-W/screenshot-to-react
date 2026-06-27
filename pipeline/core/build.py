"""Production build of the generated app (the build-success contract gate).

Deterministic tooling (no LLM): runs ``npm install`` and ``npm run build`` and
reports success/failure. Shared by the builder stage (the verify gate) and the
deployer stage (the fresh pre-deploy build).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BuildResult:
    """Outcome of an npm build/install command."""

    succeeded: bool
    stdout: str
    stderr: str

    @property
    def error_summary(self) -> str:
        """The tail of the output — compile errors live at the end."""
        tail = (self.stderr or self.stdout or "").strip().splitlines()[-40:]
        return "\n".join(tail)


def _run(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def npm_install(workdir: Path, timeout: int = 900) -> BuildResult:
    """Install dependencies into ``workdir``'s node_modules."""
    proc = _run(["npm", "install", "--no-audit", "--no-fund"], workdir, timeout)
    return BuildResult(proc.returncode == 0, proc.stdout, proc.stderr)


def build_app(workdir: Path, timeout: int = 600) -> BuildResult:
    """Run the production build — the build-success contract gate."""
    proc = _run(["npm", "run", "build"], workdir, timeout)
    return BuildResult(proc.returncode == 0, proc.stdout, proc.stderr)
