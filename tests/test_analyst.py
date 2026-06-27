"""Task 7.1 — unit-test the analyst with TestModel (deterministic output)."""

from __future__ import annotations

from pydantic_ai.models.test import TestModel

from pipeline.analyst.models import (
    Asset,
    AssetStrategy,
    ColorToken,
    ContentBlock,
    DesignTokens,
    Provenance,
    Requirements,
    ResponsiveRule,
    TypeToken,
    ViewportInference,
    ViewportKind,
)
from pipeline.analyst.stage import build_analyst_agent, run_analyst


async def test_analyst_writes_requirement_files(deps):
    agent = build_analyst_agent(model=TestModel())
    await run_analyst(deps, agent=agent)

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
        assert (deps.requirements_dir / name).is_file(), name
    assert deps.assets_dir.is_dir()


async def test_analyst_records_viewport_on_deps(deps, monkeypatch):
    """A custom output sets the inferred viewport width on deps."""

    fixed = Requirements(
        summary="A hero + CTA landing page.",
        viewport=ViewportInference(kind=ViewportKind.DESKTOP, width=1440, rationale="wide capture"),
        responsive=[
            ResponsiveRule(
                breakpoint="mobile (<768px)",
                behavior="single column",
                provenance=Provenance.ASSUMED,
            )
        ],
        assets=[
            Asset(
                name="hero",
                description="hero image slot",
                strategy=AssetStrategy.PLACEHOLDER,
                file="hero.png",
                width=1200,
                height=500,
            )
        ],
    )

    agent = build_analyst_agent(model=TestModel(custom_output_args=fixed))
    reqs = await run_analyst(deps, agent=agent)

    assert reqs.viewport.width == 1440
    assert deps.reference_viewport_width == 1440
    # Placeholder image generated at the requested size under assets/.
    placeholder = deps.assets_dir / "hero.png"
    assert placeholder.is_file()
    from PIL import Image

    assert Image.open(placeholder).size == (1200, 500)


async def test_design_tokens_and_content_written(deps):
    fixed = Requirements(
        summary="x",
        viewport=ViewportInference(kind=ViewportKind.DESKTOP, width=1440, rationale="r"),
        design_tokens=DesignTokens(
            colors=[ColorToken(name="primary", hex="#1a73e8")],
            type_scale=[TypeToken(name="h1", size="3rem", weight="700")],
            fonts=["Inter, sans-serif"],
        ),
        content=[
            ContentBlock(
                section="hero",
                headline="Welcome",
                body="Build faster.",
                ctas=["Start free trial"],
            )
        ],
    )
    agent = build_analyst_agent(model=TestModel(custom_output_args=fixed))
    await run_analyst(deps, agent=agent)

    tokens = (deps.requirements_dir / "design-tokens.md").read_text()
    content = (deps.requirements_dir / "content.md").read_text()
    assert "primary" in tokens and "#1a73e8" in tokens
    assert "Inter, sans-serif" in tokens
    assert "Welcome" in content and "Start free trial" in content


async def test_assumption_ledger_tagged(deps):
    fixed = Requirements(
        summary="x",
        viewport=ViewportInference(kind=ViewportKind.DESKTOP, width=1280, rationale="r"),
        responsive=[
            ResponsiveRule(breakpoint="mobile", behavior="stack", provenance=Provenance.ASSUMED)
        ],
    )
    agent = build_analyst_agent(model=TestModel(custom_output_args=fixed))
    await run_analyst(deps, agent=agent)
    assumptions = (deps.requirements_dir / "assumptions.md").read_text()
    responsive = (deps.requirements_dir / "responsive.md").read_text()
    assert "Assumption Ledger" in assumptions
    assert "ASSUMED" in responsive
