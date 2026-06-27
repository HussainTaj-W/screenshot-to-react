"""Builder/Verifier stage entry point (capability: react-build-verify).

Assembles ``VerifyDeps`` with agent-backed callables for code generation, build
fixing, and visual judging, then runs the verify graph and returns a
``BuildVerifyOutcome``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import BinaryContent

from ..deps import PipelineDeps
from ..graph.state import VerifyState, VisualVerdict
from ..graph.verify import VerifyDeps, build_verify_graph
from ..results import BuildVerifyOutcome
from .builder_agent import (
    build_builder_agent,
    build_fix_build_agent,
    build_judge_agent,
)


def _read_requirements_text(requirements_dir: Path) -> str:
    """Concatenate the requirement markdown files into a single prompt block."""
    parts: list[str] = []
    for name in (
        "functional.md",
        "content.md",
        "design-tokens.md",
        "visual.md",
        "non-functional.md",
        "responsive.md",
        "assumptions.md",
        "constraints.md",
        "assets.md",
    ):
        f = requirements_dir / name
        if f.is_file():
            parts.append(f"=== {name} ===\n{f.read_text()}")
    return "\n\n".join(parts)


def _is_pure_placeholder_complaint(issue: str) -> bool:
    """True if a discrepancy is only about a placeholder vs the real photo.

    These are expected and unfixable, so they should not be sent to the builder
    as work. Issues that mention size/position/layout are kept (actionable).
    """
    text = issue.lower()
    if "placeholder" not in text:
        return False
    # If it also flags a real, fixable problem, keep it.
    actionable_terms = (
        "too tall",
        "too short",
        "too wide",
        "too narrow",
        "wrong size",
        "wrong position",
        "misplaced",
        "mis-sized",
        "padding",
        "spacing",
        "shadow",
        "border",
        "alignment",
        "aspect",
        "ratio",
        "position",
        "layout",
    )
    return not any(t in text for t in actionable_terms)


def _available_assets_listing(assets_dir, requirements_dir) -> str:
    """List the actual asset files on disk with their public paths.

    Gives the builder a concrete, file-grounded checklist (the files that truly
    exist in public/), so it can wire each one to the right slot instead of
    inventing images.
    """
    from pathlib import Path

    assets_dir = Path(assets_dir)
    if not assets_dir.is_dir():
        return "(no extracted assets available)"

    files = sorted(p for p in assets_dir.iterdir() if p.is_file())
    if not files:
        return "(no extracted assets available)"

    lines = [
        "These files exist and are served from the site root. Use the path "
        "shown (the leading slash matters):",
    ]
    for f in files:
        lines.append(f"- /{f.name}")
    lines.append(
        "\nSee the `assets.md` manifest above for what each file depicts and "
        "where it belongs."
    )
    return "\n".join(lines)


def make_verify_deps(
    deps: PipelineDeps,
    *,
    skills_capabilities=None,
) -> VerifyDeps:
    """Build a ``VerifyDeps`` wired to real LLM agents.

    Per-stage models are taken from ``deps.models``. ``skills_capabilities``
    (optional list) is attached to the builder agent so it can load
    best-practice skills on demand at runtime.
    """
    builder_kwargs = {}
    if skills_capabilities:
        builder_kwargs["capabilities"] = list(skills_capabilities)

    builder_agent = build_builder_agent(deps.models.builder_model, **builder_kwargs)
    fix_agent = build_fix_build_agent(deps.models.fix_build_model)
    judge_agent = build_judge_agent(deps.models.judge_model)

    requirements_text = _read_requirements_text(deps.requirements_dir)
    reference_png = deps.reference_screenshot.read_bytes()
    available_assets = _available_assets_listing(deps.assets_dir, deps.requirements_dir)

    vdeps = VerifyDeps(
        workdir=deps.workdir,
        assets_dir=deps.assets_dir,
        requirements_dir=deps.requirements_dir,
        reference_screenshot=deps.reference_screenshot,
        gaps_report_path=deps.gaps_report_path,
        viewport_width=deps.reference_viewport_width,
        model=deps.models.builder_model,
    )

    # --- code generation -------------------------------------------------- #
    async def generate_app(vd: VerifyDeps, state: VerifyState):
        prompt: list = [
            "REQUIREMENTS:",
            requirements_text,
            "AVAILABLE ASSETS (prefer these exact paths for images; fall back to "
            "an external URL only when none fits):",
            available_assets,
            "REFERENCE SCREENSHOT:",
            BinaryContent(data=reference_png, media_type="image/png"),
        ]
        # On a fix pass, include the discrepancies and the last build screenshot.
        if state.latest_verdict is not None and state.last_build_shot is not None:
            # Filter out "placeholder instead of real photo" complaints: those are
            # expected and unfixable (the real asset doesn't exist). Keep genuine
            # layout/size/position issues, which may still mention placeholders.
            actionable = [
                d
                for d in state.latest_verdict.discrepancies
                if not _is_pure_placeholder_complaint(d.issue)
            ]
            disc = "\n".join(
                f"- {d.region} [{d.severity.value}]: {d.issue}" for d in actionable
            ) or "- (no actionable layout issues; keep current placeholders as-is)"
            prompt += [
                "Placeholder images are intentional stand-ins (correct size/"
                "position), not defects — they'll be replaced with real assets "
                "later, so don't treat them as broken. Prefer a provided/supplied "
                "asset when one fits; otherwise keep the placeholder. ONLY fix "
                "these flagged regions; leave matching regions unchanged:",
                disc,
                "YOUR LAST BUILD (for reference):",
                BinaryContent(data=state.last_build_shot, media_type="image/png"),
            ]
        result = await builder_agent.run(prompt)
        return result.output.app_jsx, result.output.index_css

    # --- build fixing ----------------------------------------------------- #
    async def fix_build(vd: VerifyDeps, state: VerifyState, app_jsx: str, index_css: str):
        prompt = [
            "BUILD ERROR:",
            state.last_build_error or "(unknown)",
            "CURRENT src/App.jsx:",
            app_jsx,
            "CURRENT src/index.css:",
            index_css,
        ]
        result = await fix_agent.run(prompt)
        return result.output.app_jsx, result.output.index_css

    # --- judging ---------------------------------------------------------- #
    async def judge(vd: VerifyDeps, state: VerifyState, build_png: bytes) -> VisualVerdict:
        prompt = [
            "REFERENCE (target):",
            BinaryContent(data=reference_png, media_type="image/png"),
            "CURRENT BUILD:",
            BinaryContent(data=build_png, media_type="image/png"),
        ]
        # History-aware: thread the prior judge run's messages.
        message_history = getattr(state, "_judge_messages", None)
        result = await judge_agent.run(prompt, message_history=message_history)
        state._judge_messages = result.all_messages()  # type: ignore[attr-defined]
        return result.output

    vdeps.generate_app = generate_app
    vdeps.fix_build = fix_build
    vdeps.judge = judge
    return vdeps


async def run_build_verify(
    deps: PipelineDeps,
    *,
    skills_capabilities=None,
    verify_deps: VerifyDeps | None = None,
) -> BuildVerifyOutcome:
    """Run the verify graph and return the outcome.

    Per-stage models come from ``deps.models``. ``verify_deps`` may be injected
    by tests to supply stub callables.
    """
    vdeps = verify_deps or make_verify_deps(
        deps, skills_capabilities=skills_capabilities
    )
    graph = build_verify_graph()
    state = VerifyState(
        build_cap=deps.build_cap,
        visual_cap=deps.visual_cap,
        similarity_threshold=deps.similarity_threshold,
    )
    outcome = await graph.run(inputs=None, state=state, deps=vdeps)
    return outcome
