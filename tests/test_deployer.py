"""Task 7.3 — deployer auth-missing and idempotency branches (mocked Netlify)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pipeline.deployer.stage import (
    DeployError,
    _read_site_id,
    _persist_site_id,
    run_deploy,
)
from pipeline.core.results import BuildVerifyOutcome, DeployOutcome


@dataclass
class _Build:
    succeeded: bool = True

    @property
    def error_summary(self) -> str:
        return "err"


def _build_ok(wd):
    return _Build(True)


async def test_refuses_when_not_building(deps):
    bv = BuildVerifyOutcome(
        built=False, matched=False, visual_attempts_used=3, build_attempts_used=3
    )
    out = await run_deploy(deps, build_verify=bv, build_runner=_build_ok)
    assert not out.deployed
    assert "does not build" in out.message


async def test_missing_token_raises(deps, monkeypatch):
    monkeypatch.delenv("NETLIFY_AUTH_TOKEN", raising=False)
    bv = BuildVerifyOutcome(
        built=True, matched=True, visual_attempts_used=0, build_attempts_used=0
    )
    with pytest.raises(DeployError):
        await run_deploy(deps, build_verify=bv, build_runner=_build_ok)


async def test_idempotent_site_reuse(deps, monkeypatch):
    monkeypatch.setenv("NETLIFY_AUTH_TOKEN", "tok")
    seen: dict = {}

    def fake_runner(d, bv, token):
        seen["site_at_call"] = _read_site_id(d)
        _persist_site_id(d, "site-123")
        return DeployOutcome(
            deployed=True, url="https://x.netlify.app", site_id="site-123"
        )

    bv = BuildVerifyOutcome(
        built=True,
        matched=False,
        visual_attempts_used=3,
        build_attempts_used=0,
        gaps_report_path=str(deps.gaps_report_path),
    )

    out1 = await run_deploy(
        deps, build_verify=bv, build_runner=_build_ok, deploy_runner=fake_runner
    )
    assert out1.deployed and seen["site_at_call"] is None

    out2 = await run_deploy(
        deps, build_verify=bv, build_runner=_build_ok, deploy_runner=fake_runner
    )
    assert out2.deployed and seen["site_at_call"] == "site-123"  # reused
