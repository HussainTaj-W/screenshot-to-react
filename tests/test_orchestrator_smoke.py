"""Tasks 7.4 & 7.5 — end-to-end smoke (no deploy) and terminal-state behavior.

Exercises the deterministic orchestrator analyst -> build/verify path with the
analyst on a TestModel and the verify graph's tooling stubbed (no real npm,
browser, or LLM for the builder). Confirms the three terminal states.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from pipeline.agents import analyst as analyst_mod
from pipeline.agents import builder as builder_mod
from pipeline.graph import scaffold as scaffold_mod
from pipeline.graph.state import Discrepancy, Severity, VisualVerdict
from pipeline.graph.verify import VerifyDeps
from pipeline.models import (
    Requirements,
    ViewportInference,
    ViewportKind,
)
from pipeline.orchestrator import run_pipeline
from pipeline.results import TerminalState
from pydantic_ai.models.test import TestModel


@dataclass
class _Build:
    succeeded: bool

    @property
    def error_summary(self) -> str:
        return "boom"


@pytest.fixture(autouse=True)
def _patch_everything(monkeypatch):
    # Analyst: deterministic requirements with a known viewport.
    fixed = Requirements(
        summary="Acme landing.",
        viewport=ViewportInference(
            kind=ViewportKind.DESKTOP, width=1440, rationale="wide"
        ),
    )

    real_build_agent = analyst_mod.build_analyst_agent

    def fake_analyst(model=None, references_dir=None):
        return real_build_agent(model=TestModel(custom_output_args=fixed))

    monkeypatch.setattr(analyst_mod, "build_analyst_agent", fake_analyst)

    # Verify graph tooling stubs (no npm/preview/browser).
    monkeypatch.setattr(scaffold_mod, "is_scaffolded", lambda wd: True)
    monkeypatch.setattr(scaffold_mod, "scaffold_app", lambda wd: None)
    monkeypatch.setattr(scaffold_mod, "npm_install", lambda wd: None)
    monkeypatch.setattr(scaffold_mod, "copy_extracted_assets", lambda a, w: [])

    class _Server:
        url = "http://127.0.0.1:0/"

        def stop(self):
            pass

    monkeypatch.setattr(scaffold_mod, "start_preview", lambda wd: _Server())


def _stub_verify_deps(deps, *, build_ok=True, match_after=1, sim=0.99) -> VerifyDeps:
    (deps.workdir / "src").mkdir(parents=True, exist_ok=True)
    (deps.workdir / "src" / "App.jsx").write_text("export default () => null")
    (deps.workdir / "src" / "index.css").write_text('@import "tailwindcss";')

    counter = {"judge": 0}
    vd = VerifyDeps(
        workdir=deps.workdir,
        assets_dir=deps.assets_dir,
        requirements_dir=deps.requirements_dir,
        reference_screenshot=deps.reference_screenshot,
        gaps_report_path=deps.gaps_report_path,
        viewport_width=deps.reference_viewport_width or 1280,
    )

    async def gen(d, s):
        (deps.workdir / "src" / "App.jsx").write_text("export default () => null")

    async def fix(d, s):
        pass

    async def judge(d, s, png):
        counter["judge"] += 1
        return VisualVerdict(
            matches=counter["judge"] >= match_after,
            similarity=sim,
            discrepancies=[Discrepancy(region="hero", issue="x", severity=Severity.MINOR)],
        )

    vd.generate_app = gen
    vd.fix_build = fix
    vd.judge = judge
    vd.build_runner = staticmethod(lambda wd: _Build(build_ok))
    vd.capture_runner = staticmethod(lambda url, viewport_width: b"PNG")
    return vd


def _patch_build_verify(monkeypatch, vd):
    """Patch run_build_verify to use the real graph with injected verify_deps."""
    real = builder_mod.run_build_verify

    async def run_bv(d, *, model=None, skills_capabilities=None, skills_capability=None):
        return await real(d, verify_deps=vd)

    monkeypatch.setattr(builder_mod, "run_build_verify", run_bv)


async def test_smoke_success_no_deploy(deps, monkeypatch):
    vd = _stub_verify_deps(deps, match_after=1)
    _patch_build_verify(monkeypatch, vd)
    result = await run_pipeline(deps, deploy=False, run_preflight_check=False)
    assert result.terminal_state is TerminalState.SUCCESS
    assert (deps.requirements_dir / "functional.md").is_file()


async def test_smoke_build_failed_no_deploy(deps, monkeypatch):
    deps.build_cap = 1
    vd = _stub_verify_deps(deps, build_ok=False)
    _patch_build_verify(monkeypatch, vd)
    result = await run_pipeline(deps, deploy=False, run_preflight_check=False)
    assert result.terminal_state is TerminalState.BUILD_FAILED


async def test_smoke_deploy_with_gaps_no_deploy(deps, monkeypatch):
    deps.visual_cap = 2
    vd = _stub_verify_deps(deps, match_after=999, sim=0.40)
    _patch_build_verify(monkeypatch, vd)
    result = await run_pipeline(deps, deploy=False, run_preflight_check=False)
    assert result.terminal_state is TerminalState.DEPLOYED_WITH_GAPS
