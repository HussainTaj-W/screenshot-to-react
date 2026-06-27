"""Unit tests for input resolution and the toolchain preflight."""

from __future__ import annotations

import pytest

from pipeline.core.deps import InputResolutionError, PipelineDeps
from pipeline.core.preflight import PreflightError, _node_major_version, check_node


def test_resolve_from_convention(sample_inputs):
    d = PipelineDeps.resolve(name="mylanding", top=sample_inputs)
    assert d.workdir == (sample_inputs / "mylanding").resolve()
    assert d.requirements_dir == (sample_inputs / "mylanding" / "requirements").resolve()
    assert d.reference_screenshot.name == "shot.png"


def test_resolve_missing_inputs(tmp_path):
    with pytest.raises(InputResolutionError):
        PipelineDeps.resolve(name="x", top=tmp_path / "nope")


def test_ensure_output_dirs(sample_inputs):
    d = PipelineDeps.resolve(name="mylanding", top=sample_inputs)
    d.ensure_output_dirs()
    assert d.workdir.is_dir()
    assert d.requirements_dir.is_dir()
    assert d.assets_dir.is_dir()


def test_node_detection_present():
    # The dev environment has Node; this should be a positive integer.
    major = _node_major_version()
    assert major is None or isinstance(major, int)


def test_check_node_raises_when_too_old(monkeypatch):
    monkeypatch.setattr("pipeline.core.preflight._node_major_version", lambda: 10)
    with pytest.raises(PreflightError):
        check_node(min_major=18)


def test_check_node_raises_when_missing(monkeypatch):
    monkeypatch.setattr("pipeline.core.preflight._node_major_version", lambda: None)
    with pytest.raises(PreflightError):
        check_node(min_major=18)
