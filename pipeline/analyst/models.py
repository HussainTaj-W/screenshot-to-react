"""Analyst data models: the ``Requirements`` contract and its sub-models.

``Requirements`` is the analyst's structured output, written to the output
project's ``requirements/`` directory and consumed by the builder. The builder's
judge verdict models live separately in ``pipeline.builder.judges``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class Provenance(str, Enum):
    """Whether a detail is evidenced by the screenshot or inferred."""

    EVIDENCED = "evidenced"  # directly visible in the screenshot
    ASSUMED = "assumed"  # inferred beyond the screenshot (must be auditable)


class AssetStrategy(str, Enum):
    RECREATE = "recreate"  # reproduce in CSS/SVG
    PLACEHOLDER = "placeholder"  # marked stand-in (builder may use external image)
    SUPPLIED = "supplied"  # a real user-provided file from the references dir


class FidelityRulingWinner(str, Enum):
    FIDELITY = "fidelity"  # reproduce the screenshot exactly
    ACCESSIBILITY = "accessibility"  # correct/accessible, accept divergence


class ViewportKind(str, Enum):
    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"


# --------------------------------------------------------------------------- #
# Requirement pieces
# --------------------------------------------------------------------------- #


class Conflict(BaseModel):
    """A recorded conflict between the instructions and the screenshot.

    Instructions always win; this records what was overridden (spec
    requirements-analysis → "Reconcile instructions and screenshot").
    """

    topic: str = Field(description="What the conflict is about, e.g. 'CTA text'.")
    instructions_value: str = Field(description="What the instructions specify.")
    screenshot_value: str = Field(description="What the screenshot shows.")
    resolution: str = Field(
        description="The chosen value (from instructions) and a short rationale."
    )


class ViewportInference(BaseModel):
    """The inferred reference viewport (spec → 'Infer reference viewport width')."""

    kind: ViewportKind
    width: int = Field(description="Pixel width to capture the built page at.")
    rationale: str = Field(description="Why this width was inferred from the shot.")


class Assumption(BaseModel):
    """An inference not directly evidenced by the screenshot.

    The assumption ledger (spec → 'Maintain an assumption ledger') stamps every
    such inference so the rebuild stays auditable and the judge's scope stays
    bounded to the shown viewport.
    """

    area: str = Field(
        description="What was assumed, e.g. 'mobile nav', 'hover state', 'breakpoint'."
    )
    assumption: str = Field(description="The specific assumed behavior.")
    basis: str = Field(description="Common-practice basis for the assumption.")


class FidelityRuling(BaseModel):
    """A per-case fidelity-vs-accessibility decision.

    Spec → 'Record fidelity-vs-accessibility rulings'.
    """

    issue: str = Field(description="The conflict, e.g. 'low-contrast hero text'.")
    winner: FidelityRulingWinner
    decision: str = Field(description="What the builder should actually do.")


class Asset(BaseModel):
    """A catalogued asset and its sourcing strategy.

    Spec → 'Catalog assets'. Assets are either recreated in code (CSS/SVG) or
    stood in as correctly-sized placeholders the user can later replace by
    dropping a real file at the same path.
    """

    name: str = Field(description="Stable file/identifier, e.g. 'logo'.")
    description: str = Field(description="What the asset is and where it appears.")
    strategy: AssetStrategy
    # Suggested filename (served from the site root as /<file>). For placeholders
    # a real image of this name is generated at the given size so the layout is
    # correct; the user replaces it later with the same filename.
    file: str | None = Field(
        default=None, description="Suggested filename served from public/ (e.g. 'hero.png')."
    )
    # Placeholder dimensions in CSS pixels, so the stand-in matches the layout.
    width: int | None = Field(
        default=None, description="Placeholder width in px (for placeholder assets)."
    )
    height: int | None = Field(
        default=None, description="Placeholder height in px (for placeholder assets)."
    )
    is_gap: bool = Field(
        default=False,
        description="True for PLACEHOLDER assets that remain a known gap.",
    )


class Section(BaseModel):
    """A functional section of the page."""

    name: str = Field(description="Section name, e.g. 'hero', 'features', 'footer'.")
    content: str = Field(description="Layout/behavior notes for the section.")
    provenance: Provenance = Provenance.EVIDENCED


# --------------------------------------------------------------------------- #
# Design tokens
# --------------------------------------------------------------------------- #


class ColorToken(BaseModel):
    name: str = Field(description="Token name, e.g. 'primary', 'surface', 'text-muted'.")
    hex: str = Field(description="Hex value, e.g. '#1a73e8'.")
    provenance: Provenance = Provenance.EVIDENCED


class ScaleToken(BaseModel):
    name: str = Field(description="Step name, e.g. 'sm', 'base', 'lg', '2xl'.")
    value: str = Field(description="CSS value, e.g. '1rem', '24px', '0.5rem'.")


class TypeToken(BaseModel):
    name: str = Field(description="Role, e.g. 'h1', 'body', 'caption'.")
    size: str = Field(description="Font size, e.g. '3rem'.")
    weight: str = Field(default="400", description="Font weight, e.g. '700'.")
    line_height: str = Field(default="", description="Optional line-height.")


class DesignTokens(BaseModel):
    """Structured design tokens the builder maps to Tailwind `@theme`."""

    colors: list[ColorToken] = Field(default_factory=list)
    spacing: list[ScaleToken] = Field(default_factory=list)
    type_scale: list[TypeToken] = Field(default_factory=list)
    radii: list[ScaleToken] = Field(default_factory=list)
    fonts: list[str] = Field(
        default_factory=list, description="Font family stacks observed/assumed."
    )


class ContentBlock(BaseModel):
    """Page copy for a section, kept separate from layout/behavior."""

    section: str = Field(description="Section name this content belongs to.")
    headline: str = Field(default="", description="Primary heading, if any.")
    body: str = Field(default="", description="Body/supporting copy.")
    ctas: list[str] = Field(default_factory=list, description="Call-to-action labels.")
    links: list[str] = Field(default_factory=list, description="Link labels/targets.")


class ResponsiveRule(BaseModel):
    """A responsive behavior rule, tagged SHOWN or ASSUMED."""

    breakpoint: str = Field(description="e.g. 'mobile (<768px)', 'tablet', 'desktop'.")
    behavior: str = Field(description="Layout/behavior at this breakpoint.")
    provenance: Provenance = Provenance.ASSUMED


class Uncertainty(BaseModel):
    """A region the analyst could not read confidently (recorded, not guessed)."""

    region: str
    note: str


# --------------------------------------------------------------------------- #
# Top-level requirements
# --------------------------------------------------------------------------- #


class Requirements(BaseModel):
    """The analyst's complete structured output.

    Written to the output project's ``requirements/`` directory as a set of
    Markdown files plus an asset manifest.
    """

    summary: str = Field(description="One-paragraph summary of the page.")

    # functional.md  (layout/behavior, not copy)
    sections: list[Section] = Field(default_factory=list)

    # content.md  (copy/CTAs/links, separate from layout)
    content: list[ContentBlock] = Field(default_factory=list)

    # design-tokens.md  (structured tokens → Tailwind @theme)
    design_tokens: DesignTokens = Field(default_factory=DesignTokens)

    # visual.md  (high-level visual prose + viewport)
    palette: list[str] = Field(
        default_factory=list, description="Key colors (hex) observed/derived."
    )
    typography: str = Field(default="", description="Type scale, families, weights.")
    layout_notes: str = Field(default="", description="Layout, spacing, grid notes.")
    viewport: ViewportInference

    # non-functional.md
    non_functional: list[str] = Field(
        default_factory=list,
        description="a11y, performance, semantic-HTML, build-success expectations.",
    )

    # responsive.md
    responsive: list[ResponsiveRule] = Field(default_factory=list)

    # assumptions.md
    assumptions: list[Assumption] = Field(default_factory=list)

    # constraints.md
    conflicts: list[Conflict] = Field(default_factory=list)
    fidelity_rulings: list[FidelityRuling] = Field(default_factory=list)
    uncertainties: list[Uncertainty] = Field(default_factory=list)

    # assets.md (+ assets/)
    assets: list[Asset] = Field(default_factory=list)
