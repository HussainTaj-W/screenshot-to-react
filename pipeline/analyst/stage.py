"""Analyst agent (capability: requirements-analysis).

Reads the instructions (text) and the reference screenshot (vision) and
produces a structured ``Requirements`` object, then writes the requirements
file set into the output project.

Key behaviors (spec ``requirements-analysis``):
- Instructions override the screenshot on conflict; conflicts are recorded.
- The reference viewport width is inferred and recorded.
- Every inference beyond the screenshot is stamped ``ASSUMED`` (ledger).
- Fidelity-vs-accessibility rulings are recorded per case.
- Assets are catalogued as recreate (CSS/SVG) or placeholder (no screenshot
  cropping; the builder reproduces or sources images).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, BinaryContent

from ..core.deps import PipelineDeps
from .models import Requirements
from .assets import realize_assets
from .writer import write_requirements

DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"

ANALYST_INSTRUCTIONS = """\
You are a meticulous front-end requirements analyst. You are given a landing-page
reference screenshot and a written instructions file. Produce a complete,
auditable requirements set for rebuilding the page in React.

You also have READ-ONLY file tools (read_file, list_directory, find_files,
search_files) scoped to the references directory. Use them to discover any extra
reference material the user provided (additional images, notes, brand files)
beyond the main screenshot, and factor it into your analysis. You cannot write
files — your analysis is returned as structured output.

Rules you MUST follow:
- When the instructions and the screenshot conflict, the INSTRUCTIONS WIN.
  Record every such conflict (topic, both values, resolution).
- Infer the viewport width the screenshot represents (mobile/tablet/desktop)
  and give the pixel width to capture the rebuilt page at.
- Anything you infer that is NOT directly visible in the screenshot (responsive
  breakpoints, mobile navigation, hover/focus states, below-the-fold content)
  MUST be recorded as an ASSUMPTION with its common-practice basis. Mark such
  responsive rules with provenance "assumed"; mark directly-visible details
  "evidenced".
- When visual fidelity conflicts with accessibility (e.g. low-contrast text
  failing WCAG), make a per-case ruling and record it.
- Catalog every asset (logo, hero image, icon, brand font). Do NOT crop the
  screenshot. For each asset choose a strategy:
  - "recreate": simple things reproducible in code (logos, icons, shapes) —
    give a filename (e.g. "logo.svg").
  - "placeholder": photographs/imagery that can't be reproduced in code — give
    a filename (e.g. "hero.png") AND the placeholder width/height in CSS pixels
    matching the slot's size/ratio in the layout (e.g. width=1200, height=500
    for a wide hero). A correctly-sized stand-in image will be generated at that
    path so the layout is right; the user replaces it later with the real file.
  Set is_gap=true for placeholders that remain unresolved.
- ICONS: explicitly list every icon visible in the screenshot in the functional
  notes (e.g. cart icon + notification badge, nav dropdown chevrons, product
  carousel left/right arrows, round "+" add buttons, star ratings, "more info"
  arrows, footer social icons, hero overlay control dots). These will be
  rendered with the lucide-react icon library, so name them clearly. Do NOT omit
  icons or treat them as decorative.
- If a region is unreadable, record it as an uncertainty rather than guessing.
- Extract STRUCTURED DESIGN TOKENS: a named color palette (token name + hex,
  e.g. primary/surface/text), a spacing scale, a type scale (role, size,
  weight), border radii, and font families. These map directly to Tailwind's
  @theme, so be precise — sample real colors from the screenshot.
- Record all page COPY (headlines, body, CTAs, links) as content blocks grouped
  by section, kept SEPARATE from the layout/behavior notes in sections.

Be specific and exhaustive. The builder and the vision judge rely entirely on
your output.
"""


def _readonly_filesystem(root: Path):
    """A FileSystem capability scoped to ``root`` with writes/edits blocked.

    ``protected_patterns=['**']`` makes every path read-only: read/list/search
    work, write/edit are rejected. Lets the analyst explore the references dir
    itself for discovery while keeping the run side-effect free.
    """
    from pydantic_ai_harness.filesystem import FileSystem

    return FileSystem(root_dir=root, protected_patterns=["**"])


def build_analyst_agent(
    model: str | None = None, *, references_dir: Path | None = None
) -> Agent[None, Requirements]:
    """Construct the analyst agent with structured ``Requirements`` output.

    When ``references_dir`` is given, the analyst also gets read-only file tools
    scoped to it, so it can discover/inspect reference files itself. The typed
    ``Requirements`` output contract is unchanged.
    """
    capabilities = []
    if references_dir is not None and Path(references_dir).is_dir():
        capabilities.append(_readonly_filesystem(Path(references_dir)))
    return Agent(
        model or DEFAULT_MODEL,
        output_type=Requirements,
        instructions=ANALYST_INSTRUCTIONS,
        capabilities=capabilities,
    )


def _screenshot_pixel_width(path: Path) -> int | None:
    """Return the screenshot's actual pixel width (the true capture width)."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            return int(im.width)
    except Exception:
        return None


def _screenshot_media_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "image/png")


async def analyze(
    deps: PipelineDeps,
    *,
    model: str | None = None,
    agent: Agent[None, Requirements] | None = None,
) -> Requirements:
    """Run the analyst agent and return the structured requirements.

    Accepts an optional pre-built ``agent`` so tests can inject a TestModel via
    ``agent.override(...)``.
    """
    agent = agent or build_analyst_agent(model, references_dir=deps.references_dir)

    instructions_text = deps.instructions_path.read_text()
    screenshot_bytes = deps.reference_screenshot.read_bytes()

    prompt = [
        "INSTRUCTIONS FILE:",
        instructions_text,
        "REFERENCE SCREENSHOT:",
        BinaryContent(
            data=screenshot_bytes,
            media_type=_screenshot_media_type(deps.reference_screenshot),
        ),
    ]

    # Supplied asset images (other files in references/). Give the analyst the
    # filename + image so it can map each to the right slot.
    if deps.supplemental_assets:
        prompt.append(
            "SUPPLIED ASSET IMAGES (real files already provided by the user; "
            "served from the site root as /<filename>). Map each appropriate one "
            "to a slot with strategy 'supplied' and file=<filename>. Do NOT make "
            "a placeholder for a slot a supplied asset fills."
        )
        for p in deps.supplemental_assets:
            prompt.append(f"Filename: {p.name}")
            prompt.append(
                BinaryContent(
                    data=p.read_bytes(), media_type=_screenshot_media_type(p)
                )
            )

    result = await agent.run(prompt)
    return result.output


async def run_analyst(
    deps: PipelineDeps,
    *,
    model: str | None = None,
    agent: Agent[None, Requirements] | None = None,
) -> Requirements:
    """Full analyst stage: analyze → extract assets → write requirements set.

    Also records the inferred viewport width back onto ``deps`` for downstream
    capture, and creates the output project directory.
    """
    deps.ensure_output_dirs()

    requirements = await analyze(deps, model=model, agent=agent)

    # The screenshot's true pixel width is the source of truth for capture width
    # (the LLM can misjudge it from a tall full-page capture). Clamp the inferred
    # width to the actual image width so the build is rendered/compared fairly.
    actual_width = _screenshot_pixel_width(deps.reference_screenshot)
    if actual_width is not None:
        if requirements.viewport.width != actual_width:
            requirements.viewport.rationale += (
                f" [Capture width overridden to the screenshot's actual width "
                f"{actual_width}px (LLM inferred {requirements.viewport.width}px).]"
            )
            requirements.viewport.width = actual_width

    # Record inferred viewport width on the shared deps for the capture step.
    deps.reference_viewport_width = requirements.viewport.width

    # Copy any user-supplied asset images from references/ into the output
    # assets dir so the build can reference them by name.
    _copy_supplied_assets(deps, requirements)

    # Generate correctly-sized placeholder images for PLACEHOLDER assets so the
    # layout is right; the user can later drop real files at the same names.
    realize_assets(requirements, deps.reference_screenshot, deps.assets_dir)

    # Write the requirements file set into the output project.
    write_requirements(requirements, deps.requirements_dir)

    return requirements


def _copy_supplied_assets(deps: PipelineDeps, requirements: Requirements) -> None:
    """Copy supplied reference images into the assets dir and ensure they are
    represented in the manifest (so the builder can reference them by name)."""
    import shutil

    from .models import Asset, AssetStrategy

    if not deps.supplemental_assets:
        return

    deps.assets_dir.mkdir(parents=True, exist_ok=True)
    mapped = {a.file for a in requirements.assets if a.file}

    for src in deps.supplemental_assets:
        dst = deps.assets_dir / src.name
        try:
            shutil.copy2(src, dst)
        except OSError:
            continue
        # If the analyst didn't map this file to a slot, add it as available so
        # the builder still sees it.
        if src.name not in mapped:
            requirements.assets.append(
                Asset(
                    name=src.stem,
                    description="User-supplied image available for use.",
                    strategy=AssetStrategy.SUPPLIED,
                    file=src.name,
                )
            )
