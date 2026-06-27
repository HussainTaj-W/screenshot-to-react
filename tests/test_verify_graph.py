"""Tasks 7.2 & 7.5 — verify graph state transitions, budgets, terminal states."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from pipeline.builder.graph import VerifyDeps, build_verify_graph
from pipeline.builder.judges import Discrepancy, Severity, VisualVerdict
from pipeline.builder.state import VerifyState
from pipeline.core import build as build_mod
from pipeline.core import preview as preview_mod
from pipeline.core import scaffold as scaffold_mod


@dataclass
class _FakeBuildResult:
    succeeded: bool

    @property
    def error_summary(self) -> str:
        return "compile error: boom"


@pytest.fixture(autouse=True)
def _stub_scaffold(monkeypatch):
    """Avoid real npm/preview/browser in graph tests."""
    monkeypatch.setattr(scaffold_mod, "is_scaffolded", lambda wd: True)
    monkeypatch.setattr(scaffold_mod, "scaffold_app", lambda wd: None)
    monkeypatch.setattr(build_mod, "npm_install", lambda wd: None)
    monkeypatch.setattr(scaffold_mod, "copy_extracted_assets", lambda a, w: [])

    class _Server:
        url = "http://127.0.0.1:0/"

        def stop(self):
            pass

    monkeypatch.setattr(preview_mod, "start_preview", lambda wd: _Server())


def _make_deps(
    tmp: Path, *, build_ok=True, match_after=1, sim=0.99, responsive_broken=None
) -> VerifyDeps:
    (tmp / "src").mkdir(parents=True, exist_ok=True)
    (tmp / "src" / "App.jsx").write_text("export default () => null")
    (tmp / "src" / "index.css").write_text('@import "tailwindcss";')

    counter = {"judge": 0}
    vd = VerifyDeps(
        workdir=tmp,
        assets_dir=tmp / "assets",
        requirements_dir=tmp / "req",
        reference_screenshot=tmp / "ref.png",
        gaps_report_path=tmp / "gaps_report.md",
        viewport_width=1280,
    )

    async def gen(d, s):
        # Coding agent writes files directly; simulate that.
        (tmp / "src" / "App.jsx").write_text("export default () => null")

    async def fix(d, s):
        (tmp / "src" / "App.jsx").write_text("export default () => null /*fixed*/")

    async def judge(d, s, png):
        counter["judge"] += 1
        return VisualVerdict(
            matches=counter["judge"] >= match_after,
            similarity=sim,
            discrepancies=[Discrepancy(region="hero", issue="too light", severity=Severity.MAJOR)],
        )

    vd.generate_app = gen
    vd.fix_build = fix
    vd.judge = judge
    vd.build_runner = staticmethod(lambda wd: _FakeBuildResult(build_ok))
    vd.capture_runner = staticmethod(lambda url, viewport_width: b"PNG")

    if responsive_broken is not None:
        from pipeline.builder.judges import ResponsiveVerdict

        async def rjudge(d, s, png):
            return ResponsiveVerdict(
                broken=responsive_broken,
                issues=(
                    [
                        Discrepancy(
                            region="page", issue="horizontal overflow", severity=Severity.MAJOR
                        )
                    ]
                    if responsive_broken
                    else []
                ),
            )

        vd.responsive_judge = rjudge
    else:
        vd.check_responsive = False
    return vd


async def test_success_on_first_match(tmp_path):
    g = build_verify_graph()
    vd = _make_deps(tmp_path, match_after=1)
    st = VerifyState(build_cap=3, visual_cap=3, similarity_threshold=0.95)
    out = await g.run(inputs=None, state=st, deps=vd)
    assert out.built and out.matched
    assert out.visual_attempts_used == 0


async def test_deploy_with_gaps_on_budget_exhaustion(tmp_path):
    g = build_verify_graph()
    # Never reaches the threshold (low similarity throughout).
    vd = _make_deps(tmp_path, match_after=999, sim=0.40)
    st = VerifyState(build_cap=3, visual_cap=3, similarity_threshold=0.95)
    out = await g.run(inputs=None, state=st, deps=vd)
    assert out.built and not out.matched
    assert out.visual_attempts_used == 3
    assert out.gaps_report_path
    assert Path(out.gaps_report_path).is_file()


async def test_similarity_threshold_blocks_match(tmp_path):
    """Similarity below T should NOT count as a match (even if judge says match)."""
    g = build_verify_graph()
    vd = _make_deps(tmp_path, match_after=1, sim=0.50)
    st = VerifyState(build_cap=1, visual_cap=2, similarity_threshold=0.95)
    out = await g.run(inputs=None, state=st, deps=vd)
    assert not out.matched
    assert out.visual_attempts_used == 2  # exhausted instead of matching


async def test_similarity_matches_despite_false_flag(tmp_path):
    """sim >= T counts as a match even when the judge's boolean flag is False.

    This is the placeholder case: high layout fidelity but the judge won't call
    gray stand-ins a true match.
    """
    g = build_verify_graph()
    vd = _make_deps(tmp_path, match_after=999, sim=0.96)  # flag always False
    st = VerifyState(build_cap=1, visual_cap=3, similarity_threshold=0.95)
    out = await g.run(inputs=None, state=st, deps=vd)
    assert out.matched
    assert out.visual_attempts_used == 0


async def test_build_failure_hard_stop(tmp_path):
    g = build_verify_graph()
    vd = _make_deps(tmp_path, build_ok=False)
    st = VerifyState(build_cap=2, visual_cap=3, similarity_threshold=0.95)
    out = await g.run(inputs=None, state=st, deps=vd)
    assert not out.built
    assert out.build_attempts_used == 2


async def test_responsive_broken_blocks_match(tmp_path):
    """Fidelity OK but mobile is objectively broken -> not a match, fixes run."""
    g = build_verify_graph()
    vd = _make_deps(tmp_path, match_after=1, sim=0.99, responsive_broken=True)
    st = VerifyState(build_cap=1, visual_cap=2, similarity_threshold=0.95)
    out = await g.run(inputs=None, state=st, deps=vd)
    assert not out.matched  # blocked by mobile breakage
    assert out.visual_attempts_used == 2  # exhausted trying to fix


async def test_responsive_ok_allows_match(tmp_path):
    """Fidelity OK and mobile sane -> match."""
    g = build_verify_graph()
    vd = _make_deps(tmp_path, match_after=1, sim=0.99, responsive_broken=False)
    st = VerifyState(build_cap=1, visual_cap=3, similarity_threshold=0.95)
    out = await g.run(inputs=None, state=st, deps=vd)
    assert out.matched
    assert out.visual_attempts_used == 0


async def test_responsive_suggestions_recorded(tmp_path):
    """Non-blocking suggestions are recorded and don't block a match."""
    from pipeline.builder.judges import ResponsiveSuggestion, ResponsiveVerdict

    g = build_verify_graph()
    vd = _make_deps(tmp_path, match_after=1, sim=0.99, responsive_broken=False)

    async def rjudge(d, s, png):
        return ResponsiveVerdict(
            broken=False,
            suggestions=[ResponsiveSuggestion(region="nav", suggestion="larger tap targets")],
        )

    vd.responsive_judge = rjudge
    st = VerifyState(build_cap=1, visual_cap=3, similarity_threshold=0.95)
    out = await g.run(inputs=None, state=st, deps=vd)
    assert out.matched  # suggestions never block
    assert st.last_responsive_suggestions
    assert any("larger tap targets" in f for f in st.quality_findings)
