"""Deployer stage (capability: netlify-deploy).

Deterministic tooling (no LLM):
- builds a fresh ``dist/`` immediately before deploy (5.1),
- requires ``NETLIFY_AUTH_TOKEN`` and fails loudly when missing (5.2),
- deploys idempotently, reusing a persisted site id when present (5.3),
- deploys the best attempt and surfaces the gaps report; only refuses to deploy
  when the app does not build (5.4).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from ..core import build as build_mod
from ..core.deps import PipelineDeps
from ..core.results import BuildVerifyOutcome, DeployOutcome


class DeployError(Exception):
    """Raised for unrecoverable deploy errors (e.g. missing auth token)."""


def _netlify_cmd() -> list[str]:
    """Return the command prefix to invoke the Netlify CLI.

    Prefers a global ``netlify`` binary; falls back to ``npx netlify``.
    """
    if shutil.which("netlify"):
        return ["netlify"]
    # Allow npx to resolve/fetch netlify-cli if it isn't on PATH (preflight
    # installs it, but not necessarily where the deployer's npx looks).
    return ["npx", "--yes", "netlify-cli"]


def _read_site_id(deps: PipelineDeps) -> str | None:
    state = deps.netlify_state_path
    if state.is_file():
        try:
            return json.loads(state.read_text()).get("siteId")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _persist_site_id(deps: PipelineDeps, site_id: str) -> None:
    state = deps.netlify_state_path
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"siteId": site_id}, indent=2))


def _run(cmd: list[str], cwd: Path, env: dict, timeout: int = 600):
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False, env=env
    )


async def run_deploy(
    deps: PipelineDeps,
    *,
    build_verify: BuildVerifyOutcome,
    build_runner=build_mod.build_app,
    deploy_runner=None,
) -> DeployOutcome:
    """Deploy the built app to Netlify.

    ``deploy_runner`` may be injected by tests to avoid real network calls.
    """
    # 5.4: refuse to deploy only when the app does not build.
    if not build_verify.deployable:
        return DeployOutcome(
            deployed=False, message="App does not build; refusing to deploy."
        )

    # 5.2: require auth token, fail loudly.
    token = os.environ.get("NETLIFY_AUTH_TOKEN")
    if not token:
        raise DeployError(
            "NETLIFY_AUTH_TOKEN is not set.\n"
            "Create a personal access token at "
            "https://app.netlify.com/user/applications#personal-access-tokens "
            "and export it as NETLIFY_AUTH_TOKEN, then re-run."
        )

    # 5.1: fresh production build immediately before deploy.
    result = build_runner(deps.workdir)
    if not result.succeeded:
        # The build passed during verify but fails now — surface clearly.
        return DeployOutcome(
            deployed=False,
            message="Fresh pre-deploy build failed:\n" + result.error_summary,
        )

    if deploy_runner is not None:
        return deploy_runner(deps, build_verify, token)

    return _netlify_deploy(deps, build_verify, token)


def _netlify_deploy(
    deps: PipelineDeps, build_verify: BuildVerifyOutcome, token: str
) -> DeployOutcome:
    env = {**os.environ, "NETLIFY_AUTH_TOKEN": token}
    site_id = _read_site_id(deps)  # 5.3: reuse if present

    cmd = _netlify_cmd() + [
        "deploy",
        "--dir",
        str(deps.dist_dir),
        "--prod",
        "--json",
    ]
    if site_id:
        cmd += ["--site", site_id]

    proc = _run(cmd, deps.workdir, env)
    if proc.returncode != 0:
        return DeployOutcome(
            deployed=False,
            message="Netlify deploy failed:\n" + (proc.stderr or proc.stdout).strip(),
        )

    url, deployed_site_id = _parse_deploy_output(proc.stdout)
    if deployed_site_id:
        _persist_site_id(deps, deployed_site_id)

    message = (
        "Deployed a visual match."
        if build_verify.matched
        else "Deployed best attempt; see gaps report for remaining discrepancies."
    )
    if build_verify.gaps_report_path:
        message += f" Gaps report: {build_verify.gaps_report_path}"

    return DeployOutcome(
        deployed=True, url=url, site_id=deployed_site_id or site_id, message=message
    )


def _parse_deploy_output(stdout: str) -> tuple[str | None, str | None]:
    """Extract the deployed URL and site id from `netlify deploy --json` output."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None, None
    url = data.get("deploy_url") or data.get("url") or data.get("ssl_url")
    site_id = data.get("site_id") or data.get("siteId")
    return url, site_id
