"""Shared pipeline dependencies and filesystem conventions.

``PipelineDeps`` is the single spine threaded through every stage (analyst,
builder, deployer). It carries resolved input/output paths, the inferred
reference viewport width, and the fix budgets.

Filesystem layout (siblings; scripts run from the repo root):

    top/
    ├── harness/          # the generator (this package lives here)
    ├── input/            # instructions.md + references/<screenshot>
    └── <name>/           # the product (parameterized by --name)
        ├── requirements/ # analyst output (+ extracted assets)
        ├── src/ …        # generated React app
        └── dist/         # built artifact → Netlify
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .config import ModelConfig

# Image extensions recognized as images (screenshot or supplied assets).
_SCREENSHOT_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Reserved base names (without extension) for the reference screenshot. Any
# other image in the references directory is treated as a supplied asset.
_SCREENSHOT_NAMES = ("screenshot", "landingpage", "reference")

# Default fix budgets (see design.md "Two budgets, not three").
DEFAULT_BUILD_CAP = 3
DEFAULT_VISUAL_CAP = 3

# Default judge similarity threshold T (tunable per design.md open questions).
DEFAULT_SIMILARITY_THRESHOLD = 0.9

# Default viewport width used only when the analyst has not yet inferred one.
DEFAULT_VIEWPORT_WIDTH = 1280

# Default mobile width for the responsive sanity check.
DEFAULT_RESPONSIVE_WIDTH = 375


class InputResolutionError(Exception):
    """Raised when the pipeline inputs cannot be resolved from the convention."""


@dataclass
class PipelineDeps:
    """Dependencies shared across all pipeline stages.

    Attributes are resolved absolute paths so stages never re-derive them.
    """

    # --- inputs ---
    instructions_path: Path
    references_dir: Path
    reference_screenshot: Path

    # --- output (the product) ---
    name: str
    workdir: Path  # the sibling <name>/ project directory
    requirements_dir: Path  # <name>/requirements
    assets_dir: Path  # <name>/requirements/assets
    dist_dir: Path  # <name>/dist

    # --- analysis-derived ---
    reference_viewport_width: int = DEFAULT_VIEWPORT_WIDTH

    # --- budgets / config ---
    build_cap: int = DEFAULT_BUILD_CAP
    visual_cap: int = DEFAULT_VISUAL_CAP
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    responsive_width: int = DEFAULT_RESPONSIVE_WIDTH
    check_responsive: bool = True

    # --- supplemental user-provided asset images (from references/) ---
    supplemental_assets: list[Path] = field(default_factory=list)

    # --- skills ---
    skills_dir: Path | None = None

    # --- deploy ---
    # An explicitly supplied Netlify site id to deploy to an existing site.
    # When None, the deployer reuses the id persisted from a prior deploy, or
    # creates a new site.
    netlify_site_id: str | None = None

    # --- models (per-stage selection) ---
    models: ModelConfig = field(default_factory=ModelConfig)

    # internal: roots, kept for derived paths and clarity
    top_dir: Path = field(default_factory=Path.cwd)

    @classmethod
    def resolve(
        cls,
        *,
        name: str,
        top: Path | str | None = None,
        input_dir: Path | str | None = None,
        instructions: Path | str | None = None,
        references_dir: Path | str | None = None,
        skills_dir: Path | str | None = None,
        build_cap: int = DEFAULT_BUILD_CAP,
        visual_cap: int = DEFAULT_VISUAL_CAP,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        responsive_width: int = DEFAULT_RESPONSIVE_WIDTH,
        check_responsive: bool = True,
        netlify_site_id: str | None = None,
        models: ModelConfig | None = None,
    ) -> PipelineDeps:
        """Resolve inputs from the ``input/`` convention and ``--name``.

        - Inputs default to ``<top>/input/instructions.md`` and
          ``<top>/input/references/`` unless explicitly overridden.
        - Output is a sibling ``<top>/<name>/`` directory.

        Raises ``InputResolutionError`` if required inputs are missing.
        """
        top_dir = Path(top).resolve() if top else Path.cwd().resolve()
        base_input = Path(input_dir).resolve() if input_dir else (top_dir / "input")

        instructions_path = (
            Path(instructions).resolve() if instructions else (base_input / "instructions.md")
        )
        refs_dir = Path(references_dir).resolve() if references_dir else (base_input / "references")

        if not instructions_path.is_file():
            raise InputResolutionError(
                f"Instructions file not found: {instructions_path}\n"
                f"Provide one at input/instructions.md or pass --instructions."
            )
        if not refs_dir.is_dir():
            raise InputResolutionError(
                f"References directory not found: {refs_dir}\n"
                f"Provide one at input/references/ or pass --references-dir."
            )

        screenshot = _find_reference_screenshot(refs_dir)
        supplied = supplemental_assets(refs_dir, screenshot)

        workdir = (top_dir / name).resolve()
        requirements_dir = workdir / "requirements"
        assets_dir = requirements_dir / "assets"
        dist_dir = workdir / "dist"

        resolved_skills_dir = (
            Path(skills_dir).resolve() if skills_dir else (top_dir / ".agents" / "skills")
        )

        # Explicit arg wins over the NETLIFY_SITE_ID env var.
        resolved_site_id = netlify_site_id or os.environ.get("NETLIFY_SITE_ID") or None
        if resolved_site_id:
            resolved_site_id = resolved_site_id.strip() or None

        return cls(
            instructions_path=instructions_path,
            references_dir=refs_dir,
            reference_screenshot=screenshot,
            supplemental_assets=supplied,
            name=name,
            workdir=workdir,
            requirements_dir=requirements_dir,
            assets_dir=assets_dir,
            dist_dir=dist_dir,
            build_cap=build_cap,
            visual_cap=visual_cap,
            similarity_threshold=similarity_threshold,
            responsive_width=responsive_width,
            check_responsive=check_responsive,
            skills_dir=resolved_skills_dir if resolved_skills_dir.is_dir() else None,
            netlify_site_id=resolved_site_id,
            models=models or ModelConfig(),
            top_dir=top_dir,
        )

    def ensure_output_dirs(self) -> None:
        """Create the output project skeleton (analyst owns first creation)."""
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.requirements_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    @property
    def gaps_report_path(self) -> Path:
        return self.workdir / "gaps_report.md"

    @property
    def netlify_state_path(self) -> Path:
        """Where the Netlify site id is persisted for idempotent re-deploys."""
        return self.workdir / ".netlify" / "state.json"


def _all_images(references_dir: Path) -> list[Path]:
    """Images directly in the references directory (top level only)."""
    return sorted(
        p for p in references_dir.iterdir() if p.is_file() and p.suffix.lower() in _SCREENSHOT_EXTS
    )


def _all_images_recursive(references_dir: Path) -> list[Path]:
    """All images under the references directory, including subfolders."""
    return sorted(
        p for p in references_dir.rglob("*") if p.is_file() and p.suffix.lower() in _SCREENSHOT_EXTS
    )


def _find_reference_screenshot(references_dir: Path) -> Path:
    """Pick the reference screenshot from the references directory.

    Prefers an image whose base name is reserved (``screenshot``,
    ``landingpage``, ``reference``). Falls back to the only image when there is
    exactly one. Raises ``InputResolutionError`` if it cannot be determined.
    """
    candidates = _all_images(references_dir)
    if not candidates:
        raise InputResolutionError(
            f"No screenshot image found in {references_dir} "
            f"(looked for {', '.join(_SCREENSHOT_EXTS)})."
        )

    # Prefer a reserved base name (case-insensitive), honoring extension order.
    by_stem = {c.stem.lower(): c for c in candidates}
    for name in _SCREENSHOT_NAMES:
        for ext in _SCREENSHOT_EXTS:
            for c in candidates:
                if c.stem.lower() == name and c.suffix.lower() == ext:
                    return c
        if name in by_stem:
            return by_stem[name]

    if len(candidates) == 1:
        return candidates[0]

    raise InputResolutionError(
        f"Multiple images in {references_dir} and none is named "
        f"{', '.join(n + '.*' for n in _SCREENSHOT_NAMES)}. Rename the reference "
        f"screenshot to e.g. 'screenshot.png' so supplied asset images aren't "
        f"mistaken for it."
    )


def supplemental_assets(references_dir: Path, screenshot: Path) -> list[Path]:
    """Image files under references/ (incl. subfolders) that are NOT the screenshot."""
    return [p for p in _all_images_recursive(references_dir) if p != screenshot]
