"""The builder/verifier ``pydantic_graph`` state machine.

States/flow (design.md):

    BUILD ──fail (build_attempts<cap)──▶ FIX_BUILD ──▶ BUILD
      │ ok                              (exhausted → build_failed)
      ▼
    QUALITY (advisory, never loops)
      ▼
    PREVIEW + CAPTURE
      ▼
    JUDGE ── matches & sim>=T ──▶ END(success)
            else visual<cap     ──▶ FIX_VISUAL ──▶ BUILD
            else                 ──▶ END(gaps → gaps_report.md)

Only the build/fix/judge nodes use the LLM; quality/preview/capture are
deterministic tooling. The graph state carries the two global budgets.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from pathlib import Path

from pydantic_graph import GraphBuilder, StepContext

from ..logging_setup import get_logger
from ..results import BuildVerifyOutcome
from . import capture as capture_mod
from . import quality as quality_mod
from . import scaffold as scaffold_mod
from .state import VerifyState, VisualVerdict

log = get_logger("verify")


@dataclass
class VerifyDeps:
    """Dependencies injected into graph steps (callables are overridable in tests)."""

    workdir: Path
    assets_dir: Path
    requirements_dir: Path
    reference_screenshot: Path
    gaps_report_path: Path
    viewport_width: int

    # responsive sanity check config
    responsive_width: int = 375
    check_responsive: bool = True

    # agents / model
    model: str | None = None

    # injectable operations (defaults call the real tooling). Tests override these.
    generate_app = None  # async callable(deps, state) -> None (agent writes files)
    fix_build = None  # async callable(deps, state) -> None (agent edits files in place)
    judge = None  # callable(deps, state, build_png) -> VisualVerdict
    responsive_judge = None  # callable(deps, state, mobile_png) -> ResponsiveVerdict
    build_runner = staticmethod(scaffold_mod.build_app)
    capture_runner = staticmethod(capture_mod.capture_page_async)


# Sentinel outputs that route the decision nodes.
@dataclass
class BuildOk:
    pass


@dataclass
class BuildFailedTerminal:
    """Build failed and the build-fix budget is exhausted (hard stop)."""


@dataclass
class JudgeMatched:
    pass


@dataclass
class JudgeNeedsFix:
    pass


@dataclass
class JudgeExhausted:
    pass


def build_verify_graph():
    """Construct (and return) the verify graph."""
    g = GraphBuilder(
        name="build-verify",
        state_type=VerifyState,
        deps_type=VerifyDeps,
        input_type=type(None),
        output_type=BuildVerifyOutcome,
    )

    # --- BUILD node (self-contained: generate, then fix until valid) ---------
    @g.step
    async def build_until_valid(ctx: StepContext[VerifyState, VerifyDeps, object]):
        """Generate the page and keep fixing compile errors until it builds.

        Internal loop: generate -> `vite build` (the static gate). While the
        build fails and the build-fix budget remains, feed the compiler error to
        the fix agent and rebuild. Returns ``BuildOk`` once it compiles, or
        ``BuildFailedTerminal`` when the budget is exhausted (hard stop).
        """
        deps = ctx.deps
        state = ctx.state

        if not scaffold_mod.is_scaffolded(deps.workdir):
            log.info("  scaffolding Vite+React+Tailwind app + npm install...")
            await asyncio.to_thread(scaffold_mod.scaffold_app, deps.workdir)
            await asyncio.to_thread(scaffold_mod.npm_install, deps.workdir)

        # The coding agent writes/edits files directly in the project.
        which = "regenerating" if state.verdict_history else "generating"
        log.info("  builder: %s page source (coding agent)...", which)
        await deps.generate_app(deps, state)

        # Copy extracted assets into public/ so the build bundles them.
        scaffold_mod.copy_extracted_assets(deps.assets_dir, deps.workdir)

        # The static gate, with an internal repair loop.
        log.info("  vite build (static gate)...")
        result = await asyncio.to_thread(deps.build_runner, deps.workdir)
        while not result.succeeded:
            state.last_build_succeeded = False
            state.last_build_error = result.error_summary
            if state.build_attempts >= state.build_cap:
                log.warning(
                    "  build failed; build-fix budget (%d) exhausted -> hard stop",
                    state.build_cap,
                )
                return BuildFailedTerminal()  # hard stop: cannot ship broken code
            state.build_attempts += 1
            log.info(
                "  build failed; fix attempt %d/%d (coding agent repairing)...",
                state.build_attempts,
                state.build_cap,
            )
            await deps.fix_build(deps, state)
            result = await asyncio.to_thread(deps.build_runner, deps.workdir)

        state.last_build_succeeded = True
        state.last_build_error = None
        log.info("  build OK")
        return BuildOk()

    # --- mark build failed (terminal) ---------------------------------------
    @g.step
    async def build_failed_terminal(
        ctx: StepContext[VerifyState, VerifyDeps, BuildFailedTerminal],
    ) -> BuildVerifyOutcome:
        ctx.state.build_failed = True
        return BuildVerifyOutcome(
            built=False,
            matched=False,
            visual_attempts_used=ctx.state.visual_attempts,
            build_attempts_used=ctx.state.build_attempts,
        )

    # --- QUALITY (advisory) --------------------------------------------------
    @g.step
    async def quality(ctx: StepContext[VerifyState, VerifyDeps, BuildOk]) -> BuildOk:
        findings = quality_mod.run_quality_checks(ctx.deps.workdir)
        ctx.state.quality_findings.extend(findings)
        return BuildOk()  # advisory: never blocks/loops

    # --- PREVIEW + CAPTURE + JUDGE ------------------------------------------
    @g.step
    async def preview_and_judge(ctx: StepContext[VerifyState, VerifyDeps, BuildOk]):
        deps = ctx.deps
        state = ctx.state

        log.info("  preview server + Playwright capture @ %dpx...", deps.viewport_width)
        server = await asyncio.to_thread(scaffold_mod.start_preview, deps.workdir)
        try:
            png = deps.capture_runner(server.url, viewport_width=deps.viewport_width)
            if inspect.isawaitable(png):
                png = await png

            mobile_png = None
            if deps.check_responsive and deps.responsive_judge is not None:
                log.info("  capture @ %dpx (mobile responsive)...", deps.responsive_width)
                mobile_png = deps.capture_runner(
                    server.url, viewport_width=deps.responsive_width
                )
                if inspect.isawaitable(mobile_png):
                    mobile_png = await mobile_png
        finally:
            await asyncio.to_thread(server.stop)

        state.last_build_shot = png
        log.info("  vision judge comparing build to reference (LLM)...")
        verdict: VisualVerdict = await deps.judge(deps, state, png)
        state.verdict_history.append(verdict)

        log.info(
            "  judge: matches=%s similarity=%.2f, %d discrepancy(ies)",
            verdict.matches,
            verdict.similarity,
            len(verdict.discrepancies),
        )
        for d in verdict.discrepancies[:8]:
            log.info("    - [%s] %s: %s", d.severity.value, d.region, d.issue)

        # Responsive sanity (mobile). No reference: judge on its own merits.
        # Objective breakage blocks the match and is added to the fix work.
        responsive_broken = False
        if mobile_png is not None:
            log.info("  responsive judge @ %dpx (LLM)...", deps.responsive_width)
            rv = await deps.responsive_judge(deps, state, mobile_png)
            responsive_broken = rv.broken
            log.info(
                "  responsive: broken=%s, %d issue(s), %d suggestion(s)",
                rv.broken,
                len(rv.issues),
                len(rv.suggestions),
            )
            if rv.broken:
                for d in rv.issues:
                    log.info("    - [%s] %s: %s", d.severity.value, d.region, d.issue)
                # Surface objective breakage to the builder as discrepancies.
                verdict.discrepancies.extend(rv.issues)
                state.last_responsive_issues = list(rv.issues)
            else:
                state.last_responsive_issues = []

            # Non-blocking suggestions: cap to the top few high-impact ones so
            # the builder isn't flooded with trivia.
            state.last_responsive_suggestions = list(rv.suggestions)[:3]
            for s in state.last_responsive_suggestions:
                log.info("    ~ suggest [%s]: %s", s.region, s.suggestion)
                state.quality_findings.append(
                    f"Responsive ({deps.responsive_width}px) suggestion "
                    f"[{s.region}]: {s.suggestion}"
                )

        # Match on similarity threshold alone (placeholders OK), AND mobile must
        # not be objectively broken.
        fidelity_ok = verdict.similarity >= state.similarity_threshold
        is_match = fidelity_ok and not responsive_broken
        if is_match:
            state.matched = True
            log.info("  MATCH reached (similarity %.2f >= T %.2f, responsive OK)",
                     verdict.similarity, state.similarity_threshold)
            return JudgeMatched()
        if fidelity_ok and responsive_broken:
            log.info("  fidelity OK but mobile layout is broken -> needs fix")
        if state.visual_attempts < state.visual_cap:
            return JudgeNeedsFix()
        log.info("  visual-fix budget (%d) exhausted -> emitting gaps report",
                 state.visual_cap)
        return JudgeExhausted()

    # --- FIX_VISUAL ----------------------------------------------------------
    @g.step
    async def fix_visual(ctx: StepContext[VerifyState, VerifyDeps, JudgeNeedsFix]):
        ctx.state.visual_attempts += 1
        log.info(
            "  visual fix attempt %d/%d -> regenerating flagged regions",
            ctx.state.visual_attempts,
            ctx.state.visual_cap,
        )
        return None  # routes back to build (regenerate addressing discrepancies)

    # --- success terminal ----------------------------------------------------
    @g.step
    async def success_terminal(
        ctx: StepContext[VerifyState, VerifyDeps, JudgeMatched],
    ) -> BuildVerifyOutcome:
        v = ctx.state.latest_verdict
        return BuildVerifyOutcome(
            built=True,
            matched=True,
            visual_attempts_used=ctx.state.visual_attempts,
            build_attempts_used=ctx.state.build_attempts,
            similarity=v.similarity if v else None,
            discrepancies=[d.model_dump() for d in (v.discrepancies if v else [])],
        )

    # --- gaps terminal -------------------------------------------------------
    @g.step
    async def gaps_terminal(
        ctx: StepContext[VerifyState, VerifyDeps, JudgeExhausted],
    ) -> BuildVerifyOutcome:
        v = ctx.state.latest_verdict
        gaps_path = _write_gaps_report(ctx.deps, ctx.state)
        return BuildVerifyOutcome(
            built=True,
            matched=False,
            visual_attempts_used=ctx.state.visual_attempts,
            build_attempts_used=ctx.state.build_attempts,
            similarity=v.similarity if v else None,
            discrepancies=[d.model_dump() for d in (v.discrepancies if v else [])],
            gaps_report_path=str(gaps_path),
        )

    # --- decisions -----------------------------------------------------------
    build_decision = (
        g.decision(note="build valid?")
        .branch(g.match(BuildOk).to(quality))
        .branch(g.match(BuildFailedTerminal).to(build_failed_terminal))
    )

    judge_decision = (
        g.decision(note="judge verdict?")
        .branch(g.match(JudgeMatched).to(success_terminal))
        .branch(g.match(JudgeNeedsFix).to(fix_visual))
        .branch(g.match(JudgeExhausted).to(gaps_terminal))
    )

    g.add(
        g.edge_from(g.start_node).to(build_until_valid),
        g.edge_from(build_until_valid).to(build_decision),
        g.edge_from(quality).to(preview_and_judge),
        g.edge_from(preview_and_judge).to(judge_decision),
        # A visual fix regenerates the page, which re-enters the build loop.
        g.edge_from(fix_visual).to(build_until_valid),
        g.edge_from(success_terminal).to(g.end_node),
        g.edge_from(gaps_terminal).to(g.end_node),
        g.edge_from(build_failed_terminal).to(g.end_node),
    )

    return g.build()


def _write_gaps_report(deps: VerifyDeps, state: VerifyState) -> Path:
    v = state.latest_verdict
    lines = [
        "# Gaps Report",
        "",
        f"Visual fix budget ({state.visual_cap}) exhausted without a full match.",
        "",
        f"- Final similarity estimate: {v.similarity if v else 'n/a'}",
        f"- Visual fix attempts used: {state.visual_attempts}",
        "",
        "## Remaining visual discrepancies",
        "",
    ]
    if v and v.discrepancies:
        for d in v.discrepancies:
            lines.append(f"- **{d.region}** [{d.severity.value}]: {d.issue}")
    else:
        lines.append("- (none recorded)")
    lines.append("")
    if state.quality_findings:
        lines.append("## Advisory quality findings")
        lines.append("")
        lines.extend(f"- {f}" for f in state.quality_findings)
        lines.append("")
    deps.gaps_report_path.write_text("\n".join(lines))
    return deps.gaps_report_path
