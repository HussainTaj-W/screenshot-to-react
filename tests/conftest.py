"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pipeline.deps import PipelineDeps


@pytest.fixture
def sample_inputs(tmp_path: Path) -> Path:
    """Create a minimal input/ tree (instructions + a real PNG) under tmp_path."""
    refs = tmp_path / "input" / "references"
    refs.mkdir(parents=True)
    (tmp_path / "input" / "instructions.md").write_text(
        "Landing page for Acme. Primary CTA text: 'Start free trial'."
    )
    Image.new("RGB", (1440, 900), (245, 245, 245)).save(refs / "shot.png")
    return tmp_path


@pytest.fixture
def deps(sample_inputs: Path) -> PipelineDeps:
    d = PipelineDeps.resolve(name="mylanding", top=sample_inputs)
    d.ensure_output_dirs()
    return d
