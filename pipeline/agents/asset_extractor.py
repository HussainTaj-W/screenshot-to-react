"""Realize catalogued assets as files.

No screenshot cropping (unreliable on tall full-page captures). Instead:

- ``RECREATE`` assets are left for the builder to reproduce in inline SVG/CSS;
  here we only ensure a stable suggested filename.
- ``PLACEHOLDER`` assets get a real, correctly-sized placeholder image written
  to disk (neutral background + a centered label). The build references it by
  filename, so the layout is correct immediately and the user can later replace
  the file with a real asset of the same name.

Spec ``requirements-analysis`` → "Catalog assets".
"""

from __future__ import annotations

from pathlib import Path

from ..models import AssetStrategy, Requirements

# Default placeholder size when the analyst doesn't specify one.
_DEFAULT_W = 800
_DEFAULT_H = 600


def realize_assets(
    requirements: Requirements,
    reference_screenshot: Path,  # kept for signature stability; unused now
    assets_dir: Path,
) -> list[str]:
    """Generate placeholder image files for PLACEHOLDER assets.

    Mutates each asset's ``file`` to a stable filename. Returns the list of
    files written. RECREATE assets are not written (the builder makes them).
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for asset in requirements.assets:
        suggested = asset.file or f"{_safe(asset.name)}{_ext_for(asset)}"
        asset.file = suggested

        if asset.strategy is AssetStrategy.PLACEHOLDER:
            w = asset.width or _DEFAULT_W
            h = asset.height or _DEFAULT_H
            _write_placeholder(assets_dir / suggested, w, h, asset.name)
            written.append(suggested)

    return written


def _write_placeholder(path: Path, width: int, height: int, label: str) -> None:
    """Write a neutral placeholder PNG of the given size with a centered label."""
    from PIL import Image, ImageDraw

    width = max(1, int(width))
    height = max(1, int(height))
    img = Image.new("RGB", (width, height), (228, 228, 231))  # neutral zinc-200
    draw = ImageDraw.Draw(img)

    # Border so the placeholder reads as intentional.
    draw.rectangle([0, 0, width - 1, height - 1], outline=(161, 161, 170), width=2)

    text = f"{label}\n{width}x{height}"
    # Centered multiline text (default bitmap font; no external font needed).
    try:
        bbox = draw.multiline_textbbox((0, 0), text, align="center")
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = len(label) * 6, 20
    draw.multiline_text(
        ((width - tw) / 2, (height - th) / 2),
        text,
        fill=(113, 113, 122),
        align="center",
    )
    img.save(path)


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower()).strip("-") or "asset"


def _ext_for(asset) -> str:
    if asset.strategy is AssetStrategy.RECREATE:
        return ".svg"
    return ".png"
