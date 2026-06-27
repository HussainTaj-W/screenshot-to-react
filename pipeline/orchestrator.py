"""Deterministic top-level orchestration.

This is plain Python, not an LLM agent: the analyst → builder → deployer order
never branches, so no model decides control flow (see design.md decision 1).
The only branching/looping lives inside the builder's ``pydantic_graph``.

Flow:

    preflight → analyst → builder/verify ─┬─ build failed ─→ HARD STOP (no deploy)
                                          └─ builds ───────→ deployer
                                                              ├─ matched   → SUCCESS
                                                              └─ has gaps  → DEPLOYED_WITH_GAPS
"""

from __future__ import annotations

from .deps import PipelineDeps
from .logging_setup import get_logger
from .preflight import run_preflight
from .results import (
    BuildVerifyOutcome,
    PipelineResult,
    TerminalState,
)

log = get_logger()


async def run_pipeline(
    deps: PipelineDeps,
    *,
    deploy: bool = True,
    run_preflight_check: bool = True,
    model: str | None = None,
) -> PipelineResult:
    """Run the full pipeline deterministically and return the terminal result.

    ``deploy=False`` runs analyst + build/verify only (used by the e2e smoke
    test). ``model`` is a global override; per-stage models come from
    ``deps.models`` (a :class:`ModelConfig`).
    """
    # Imported lazily so the orchestrator module stays importable even while
    # individual stages are still under construction / for targeted unit tests.
    from .agents.analyst import run_analyst
    from .agents.builder import run_build_verify
    from .agents.deployer import run_deploy

    # A passed global ``model`` sets the config default when not already set.
    if model and not deps.models.default:
        deps.models.default = model

    log.info("Pipeline start: name=%s deploy=%s", deps.name, deploy)
    log.info(
        "Models: analyst=%s builder=%s fix_build=%s judge=%s",
        deps.models.analyst_model,
        deps.models.builder_model,
        deps.models.fix_build_model,
        deps.models.judge_model,
    )

    # 0. Toolchain preflight (idempotent; pass-through when satisfied).
    if run_preflight_check:
        log.info("Preflight: verifying toolchain...")
        result = run_preflight(require_netlify=deploy)
        log.info(
            "Preflight OK (present=%s installed=%s)",
            ", ".join(result.already_present) or "-",
            ", ".join(result.installed) or "none",
        )

    # 1. Analyst — owns first creation of the output project dir.
    deps.ensure_output_dirs()
    log.info("Stage 1/3 — Analyst: reading instructions + screenshot...")
    requirements = await run_analyst(deps, model=deps.models.analyst_model)
    log.info(
        "Analyst done: %d sections, %d assets, viewport=%dpx, %d assumptions, "
        "%d conflicts. Requirements -> %s",
        len(requirements.sections),
        len(requirements.assets),
        deps.reference_viewport_width,
        len(requirements.assumptions),
        len(requirements.conflicts),
        deps.requirements_dir,
    )

    # 2. Builder / Verifier. Mount runtime skills on the builder agent and
    #    track whether the model actually loads any of them.
    from .skills import build_skills_capabilities

    skills_caps, skills_usage = build_skills_capabilities(deps.skills_dir)
    log.info(
        "Stage 2/3 — Builder/Verifier: scaffolding + build/verify loop "
        "(build_cap=%d, visual_cap=%d, T=%.2f)...",
        deps.build_cap,
        deps.visual_cap,
        deps.similarity_threshold,
    )
    build_verify: BuildVerifyOutcome = await run_build_verify(
        deps, skills_capabilities=skills_caps
    )
    log.info(
        "Builder/Verifier done: built=%s matched=%s similarity=%s "
        "(build_fixes=%d, visual_fixes=%d)",
        build_verify.built,
        build_verify.matched,
        f"{build_verify.similarity:.2f}" if build_verify.similarity is not None else "n/a",
        build_verify.build_attempts_used,
        build_verify.visual_attempts_used,
    )
    if skills_usage is not None:
        log.info(skills_usage.summary())

    # Terminal state: hard stop if the app does not build.
    if not build_verify.deployable:
        log.warning("Build failed after build-fix budget; hard stop, not deploying.")
        return PipelineResult(
            terminal_state=TerminalState.BUILD_FAILED,
            name=deps.name,
            build_verify=build_verify,
            message=(
                "Build failed after exhausting the build-fix budget "
                f"({deps.build_cap}); not deploying."
            ),
        )

    if build_verify.gaps_report_path:
        log.info("Gaps report written -> %s", build_verify.gaps_report_path)

    if not deploy:
        log.info("Deploy disabled (--no-deploy); stopping after local build/verify.")
        # Local-only run (e.g. smoke test): no deployment attempted.
        state = (
            TerminalState.SUCCESS
            if build_verify.matched
            else TerminalState.DEPLOYED_WITH_GAPS
        )
        return PipelineResult(
            terminal_state=state,
            name=deps.name,
            build_verify=build_verify,
            message="Deploy disabled; local build/verify only.",
        )

    # 3. Deployer — deploys best attempt; gaps surfaced when not matched.
    log.info("Stage 3/3 — Deployer: fresh build + Netlify deploy...")
    deploy_outcome = await run_deploy(deps, build_verify=build_verify)
    log.info(
        "Deployer done: deployed=%s url=%s",
        deploy_outcome.deployed,
        deploy_outcome.url or "-",
    )

    # The deploy itself may fail (e.g. bad token); reflect that honestly rather
    # than reporting success based only on the visual outcome.
    if not deploy_outcome.deployed:
        return PipelineResult(
            terminal_state=TerminalState.DEPLOY_FAILED,
            name=deps.name,
            build_verify=build_verify,
            deploy=deploy_outcome,
            message=(
                "Build succeeded but deployment failed: "
                f"{deploy_outcome.message}"
            ),
        )

    state = (
        TerminalState.SUCCESS
        if build_verify.matched
        else TerminalState.DEPLOYED_WITH_GAPS
    )
    return PipelineResult(
        terminal_state=state,
        name=deps.name,
        build_verify=build_verify,
        deploy=deploy_outcome,
        message=(
            "Deployed a visual match."
            if build_verify.matched
            else "Deployed best attempt; see gaps report for remaining discrepancies."
        ),
    )
