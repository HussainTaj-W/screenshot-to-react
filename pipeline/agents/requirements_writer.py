"""Render a ``Requirements`` model into the output project's requirements set.

Writes the Markdown file set described in spec ``requirements-analysis`` →
"Write requirements into the output project":

    requirements/
      functional.md  visual.md  non-functional.md
      responsive.md  assumptions.md  constraints.md
      assets.md
      assets/          (extracted/recreated asset files)
"""

from __future__ import annotations

from pathlib import Path

from ..models import Provenance, Requirements


def _provenance_tag(p: Provenance) -> str:
    return "ASSUMED" if p is Provenance.ASSUMED else "SHOWN"


def write_requirements(requirements: Requirements, requirements_dir: Path) -> dict[str, Path]:
    """Write all requirement Markdown files. Returns a map of name -> path."""
    requirements_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    written["functional"] = _write_functional(requirements, requirements_dir)
    written["content"] = _write_content(requirements, requirements_dir)
    written["design-tokens"] = _write_design_tokens(requirements, requirements_dir)
    written["visual"] = _write_visual(requirements, requirements_dir)
    written["non-functional"] = _write_non_functional(requirements, requirements_dir)
    written["responsive"] = _write_responsive(requirements, requirements_dir)
    written["assumptions"] = _write_assumptions(requirements, requirements_dir)
    written["constraints"] = _write_constraints(requirements, requirements_dir)
    written["assets"] = _write_assets_manifest(requirements, requirements_dir)

    return written


def _write_functional(r: Requirements, d: Path) -> Path:
    lines = ["# Functional Requirements", "", f"{r.summary}", ""]
    for s in r.sections:
        lines.append(f"## {s.name}  ({_provenance_tag(s.provenance)})")
        lines.append("")
        lines.append(s.content)
        lines.append("")
    path = d / "functional.md"
    path.write_text("\n".join(lines))
    return path


def _write_content(r: Requirements, d: Path) -> Path:
    lines = [
        "# Content",
        "",
        "All page copy, CTAs, and links — kept separate from layout/behavior.",
        "",
    ]
    if r.content:
        for c in r.content:
            lines.append(f"## {c.section}")
            lines.append("")
            if c.headline:
                lines.append(f"- **Headline:** {c.headline}")
            if c.body:
                lines.append(f"- **Body:** {c.body}")
            if c.ctas:
                lines.append(f"- **CTAs:** {', '.join(c.ctas)}")
            if c.links:
                lines.append(f"- **Links:** {', '.join(c.links)}")
            lines.append("")
    else:
        lines.append("(no content recorded)")
        lines.append("")
    path = d / "content.md"
    path.write_text("\n".join(lines))
    return path


def _write_design_tokens(r: Requirements, d: Path) -> Path:
    t = r.design_tokens
    lines = [
        "# Design Tokens",
        "",
        "Structured tokens for the builder to map into Tailwind `@theme`.",
        "",
        "## Colors",
        "",
    ]
    if t.colors:
        lines.append("| Token | Hex | Provenance |")
        lines.append("| ----- | --- | ---------- |")
        for c in t.colors:
            lines.append(f"| {c.name} | `{c.hex}` | {_provenance_tag(c.provenance)} |")
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("## Spacing scale")
    lines.append("")
    if t.spacing:
        lines.extend(f"- `{s.name}` = {s.value}" for s in t.spacing)
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("## Type scale")
    lines.append("")
    if t.type_scale:
        lines.append("| Role | Size | Weight | Line height |")
        lines.append("| ---- | ---- | ------ | ----------- |")
        for ty in t.type_scale:
            lines.append(f"| {ty.name} | {ty.size} | {ty.weight} | {ty.line_height} |")
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("## Radii")
    lines.append("")
    if t.radii:
        lines.extend(f"- `{rr.name}` = {rr.value}" for rr in t.radii)
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("## Fonts")
    lines.append("")
    if t.fonts:
        lines.extend(f"- {f}" for f in t.fonts)
    else:
        lines.append("- (none recorded)")
    lines.append("")

    path = d / "design-tokens.md"
    path.write_text("\n".join(lines))
    return path


def _write_visual(r: Requirements, d: Path) -> Path:
    lines = ["# Visual Requirements", ""]
    lines.append("## Viewport")
    lines.append("")
    lines.append(
        f"- Inferred: **{r.viewport.kind.value}** at **{r.viewport.width}px**"
    )
    lines.append(f"- Rationale: {r.viewport.rationale}")
    lines.append("")
    lines.append("## Palette")
    lines.append("")
    lines.extend(f"- `{c}`" for c in r.palette) if r.palette else lines.append("- (none recorded)")
    lines.append("")
    lines.append("## Typography")
    lines.append("")
    lines.append(r.typography or "(none recorded)")
    lines.append("")
    lines.append("## Layout")
    lines.append("")
    lines.append(r.layout_notes or "(none recorded)")
    lines.append("")
    path = d / "visual.md"
    path.write_text("\n".join(lines))
    return path


def _write_non_functional(r: Requirements, d: Path) -> Path:
    lines = ["# Non-Functional Requirements", ""]
    if r.non_functional:
        lines.extend(f"- {item}" for item in r.non_functional)
    else:
        lines.append("- (none recorded)")
    lines.append("")
    lines.append("> The generated app MUST compile successfully (build-success contract).")
    lines.append("")
    path = d / "non-functional.md"
    path.write_text("\n".join(lines))
    return path


def _write_responsive(r: Requirements, d: Path) -> Path:
    lines = [
        "# Responsive Behavior",
        "",
        "Each rule is tagged `SHOWN` (evidenced by the screenshot) or "
        "`ASSUMED` (inferred, see assumptions.md).",
        "",
    ]
    if r.responsive:
        for rule in r.responsive:
            lines.append(
                f"- **{rule.breakpoint}** ({_provenance_tag(rule.provenance)}): "
                f"{rule.behavior}"
            )
    else:
        lines.append("- (none recorded)")
    lines.append("")
    path = d / "responsive.md"
    path.write_text("\n".join(lines))
    return path


def _write_assumptions(r: Requirements, d: Path) -> Path:
    lines = [
        "# Assumption Ledger",
        "",
        "Everything inferred beyond the screenshot. The vision judge does NOT "
        "verify these; they keep the rebuild auditable and honest.",
        "",
    ]
    if r.assumptions:
        for a in r.assumptions:
            lines.append(f"## {a.area}")
            lines.append("")
            lines.append(f"- **Assumption:** {a.assumption}")
            lines.append(f"- **Basis:** {a.basis}")
            lines.append("")
    else:
        lines.append("(no assumptions recorded)")
        lines.append("")
    path = d / "assumptions.md"
    path.write_text("\n".join(lines))
    return path


def _write_constraints(r: Requirements, d: Path) -> Path:
    lines = ["# Constraints & Rulings", ""]

    lines.append("## Conflict Resolution (instructions override screenshot)")
    lines.append("")
    if r.conflicts:
        for c in r.conflicts:
            lines.append(f"- **{c.topic}**")
            lines.append(f"  - Instructions: {c.instructions_value}")
            lines.append(f"  - Screenshot: {c.screenshot_value}")
            lines.append(f"  - Resolution: {c.resolution}")
    else:
        lines.append("- (no conflicts)")
    lines.append("")

    lines.append("## Fidelity vs. Accessibility Rulings")
    lines.append("")
    if r.fidelity_rulings:
        for fr in r.fidelity_rulings:
            lines.append(f"- **{fr.issue}** → winner: `{fr.winner.value}`")
            lines.append(f"  - Decision: {fr.decision}")
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Uncertainties (unreadable regions, recorded not guessed)")
    lines.append("")
    if r.uncertainties:
        for u in r.uncertainties:
            lines.append(f"- **{u.region}**: {u.note}")
    else:
        lines.append("- (none)")
    lines.append("")

    path = d / "constraints.md"
    path.write_text("\n".join(lines))
    return path


def _write_assets_manifest(r: Requirements, d: Path) -> Path:
    lines = [
        "# Asset Manifest",
        "",
        "Strategy per asset: `recreate` (inline SVG/CSS) or `placeholder` "
        "(a correctly-sized stand-in image generated at the given path; replace "
        "with the real asset using the same filename).",
        "",
        "| Name | Strategy | File | Size | Description | Gap |",
        "| ---- | -------- | ---- | ---- | ----------- | --- |",
    ]
    for a in r.assets:
        size = f"{a.width}x{a.height}" if (a.width and a.height) else ""
        gap = "yes" if a.is_gap else ""
        lines.append(
            f"| {a.name} | {a.strategy.value} | {a.file or ''} | {size} | "
            f"{a.description} | {gap} |"
        )
    if not r.assets:
        lines.append("| (none) | | | | | |")
    lines.append("")
    path = d / "assets.md"
    path.write_text("\n".join(lines))
    return path
