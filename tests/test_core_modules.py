"""Unit tests for core modules: build, capture, scaffold, config.

These modules are deterministic tooling (no LLM calls), so tests use
tmp_path fixtures and monkeypatching to avoid real npm/Playwright.
"""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

from pipeline.core.build import BuildResult, build_app, npm_install
from pipeline.core.config import DEFAULT_MODEL, ModelConfig
from pipeline.core.results import BuildVerifyOutcome, DeployOutcome, PipelineResult, TerminalState
from pipeline.core.scaffold import copy_extracted_assets, is_scaffolded

# ── build.py ──────────────────────────────────────────────────────────────────


class TestBuildResult:
    def test_success(self):
        r = BuildResult(succeeded=True, stdout="ok", stderr="")
        assert r.succeeded
        assert r.error_summary == "ok"

    def test_failure(self):
        r = BuildResult(succeeded=False, stdout="", stderr="Error: build failed")
        assert not r.succeeded
        assert "build failed" in r.error_summary

    def test_error_summary_tail(self):
        lines = [f"line{i}" for i in range(50)]
        r = BuildResult(succeeded=False, stdout="", stderr="\n".join(lines))
        summary = r.error_summary
        # Should be at most 40 lines, containing the last lines.
        assert summary.count("\n") <= 39
        assert "line49" in summary

    def test_prefers_stderr_over_stdout(self):
        r = BuildResult(succeeded=False, stdout="stdout msg", stderr="stderr msg")
        assert "stderr msg" in r.error_summary


class TestNpmInstall:
    def test_success(self, monkeypatch):
        def fake_run(cmd, cwd, timeout):
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="done", stderr="")

        monkeypatch.setattr("pipeline.core.build._run", fake_run)
        result = npm_install(Path("/tmp/workdir"))
        assert result.succeeded

    def test_failure(self, monkeypatch):
        def fake_run(cmd, cwd, timeout):
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="install failed"
            )

        monkeypatch.setattr("pipeline.core.build._run", fake_run)
        result = npm_install(Path("/tmp/workdir"))
        assert not result.succeeded
        assert "install failed" in result.stderr

    def test_uses_correct_args(self, monkeypatch):
        captured = []

        def fake_run(cmd, cwd, timeout):
            captured.extend(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        monkeypatch.setattr("pipeline.core.build._run", fake_run)
        npm_install(Path("/tmp/wd"))
        assert captured == ["npm", "install", "--no-audit", "--no-fund"]


class TestBuildApp:
    def test_success(self, monkeypatch):
        def fake_run(cmd, cwd, timeout):
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="built", stderr="")

        monkeypatch.setattr("pipeline.core.build._run", fake_run)
        result = build_app(Path("/tmp/workdir"))
        assert result.succeeded

    def test_failure(self, monkeypatch):
        def fake_run(cmd, cwd, timeout):
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="build error"
            )

        monkeypatch.setattr("pipeline.core.build._run", fake_run)
        result = build_app(Path("/tmp/workdir"))
        assert not result.succeeded

    def test_uses_correct_args(self, monkeypatch):
        captured = []

        def fake_run(cmd, cwd, timeout):
            captured.extend(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        monkeypatch.setattr("pipeline.core.build._run", fake_run)
        build_app(Path("/tmp/wd"))
        assert captured == ["npm", "run", "build"]


# ── scaffold.py ──────────────────────────────────────────────────────────────


class TestIsScaffolded:
    def test_returns_true_when_both_exist(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "src").mkdir()
        assert is_scaffolded(tmp_path)

    def test_returns_false_without_package_json(self, tmp_path):
        (tmp_path / "src").mkdir()
        assert not is_scaffolded(tmp_path)

    def test_returns_false_without_src(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        assert not is_scaffolded(tmp_path)

    def test_returns_false_for_empty_dir(self, tmp_path):
        assert not is_scaffolded(tmp_path)


class TestCopyExtractedAssets:
    def test_copies_files_to_public(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "hero.png").write_bytes(b"png")
        (assets_dir / "logo.svg").write_bytes(b"svg")

        workdir = tmp_path / "app"
        workdir.mkdir()

        copied = copy_extracted_assets(assets_dir, workdir)
        assert sorted(copied) == ["hero.png", "logo.svg"]
        assert (workdir / "public" / "hero.png").read_bytes() == b"png"
        assert (workdir / "public" / "logo.svg").read_bytes() == b"svg"

    def test_skips_directories(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "sub").mkdir()
        (assets_dir / "file.txt").write_text("hi")

        workdir = tmp_path / "app"
        workdir.mkdir()

        copied = copy_extracted_assets(assets_dir, workdir)
        assert copied == ["file.txt"]
        assert not (workdir / "public" / "sub").exists()

    def test_returns_empty_when_no_assets_dir(self, tmp_path):
        workdir = tmp_path / "app"
        workdir.mkdir()

        copied = copy_extracted_assets(tmp_path / "nonexistent", workdir)
        assert copied == []

    def test_creates_public_dir(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "img.png").write_bytes(b"img")

        copied = copy_extracted_assets(assets_dir, tmp_path)
        assert (tmp_path / "public").is_dir()
        assert copied == ["img.png"]


# ── config.py ────────────────────────────────────────────────────────────────


class TestModelConfigFromEnv:
    def test_empty_env_uses_defaults(self):
        cfg = ModelConfig.from_env({})
        assert cfg.default is None
        assert cfg.analyst is None
        assert cfg.builder is None
        assert cfg.fix_build is None
        assert cfg.judge is None

    def test_parses_env_variables(self):
        env = {
            "PIPELINE_MODEL": "openai:gpt-4",
            "PIPELINE_MODEL_ANALYST": "openai:gpt-4-vision",
            "PIPELINE_MODEL_BUILDER": "anthropic:claude-3",
            "PIPELINE_MODEL_FIX_BUILD": "openai:gpt-4-mini",
            "PIPELINE_MODEL_JUDGE": "anthropic:claude-3-vision",
        }
        cfg = ModelConfig.from_env(env)
        assert cfg.default == "openai:gpt-4"
        assert cfg.analyst == "openai:gpt-4-vision"
        assert cfg.builder == "anthropic:claude-3"
        assert cfg.fix_build == "openai:gpt-4-mini"
        assert cfg.judge == "anthropic:claude-3-vision"

    def test_ignores_empty_values(self):
        env = {
            "PIPELINE_MODEL": "",
            "PIPELINE_MODEL_ANALYST": "   ",
        }
        cfg = ModelConfig.from_env(env)
        assert cfg.default is None
        assert cfg.analyst is None

    def test_strips_whitespace(self):
        cfg = ModelConfig.from_env({"PIPELINE_MODEL": "  openai:gpt-4  "})
        assert cfg.default == "openai:gpt-4"


class TestModelConfigResolution:
    def test_analyst_falls_back_to_default(self):
        cfg = ModelConfig(default="openai:gpt-4", analyst=None)
        assert cfg.analyst_model == "openai:gpt-4"

    def test_analyst_uses_explicit_value(self):
        cfg = ModelConfig(default="openai:gpt-4", analyst="anthropic:claude-3")
        assert cfg.analyst_model == "anthropic:claude-3"

    def test_builder_uses_explicit_value(self):
        cfg = ModelConfig(default="openai:gpt-4", builder="anthropic:claude-3")
        assert cfg.builder_model == "anthropic:claude-3"

    def test_builder_falls_back_to_default(self):
        cfg = ModelConfig(default="openai:gpt-4")
        assert cfg.builder_model == "openai:gpt-4"

    def test_fix_build_falls_back_to_builder_then_default(self):
        cfg = ModelConfig(default="openai:gpt-4", builder="anthropic:claude-3")
        assert cfg.fix_build_model == "anthropic:claude-3"

    def test_fix_build_uses_explicit_value(self):
        cfg = ModelConfig(
            default="openai:gpt-4",
            builder="anthropic:claude-3",
            fix_build="openai:gpt-4-mini",
        )
        assert cfg.fix_build_model == "openai:gpt-4-mini"

    def test_fix_build_falls_back_to_module_default(self):
        cfg = ModelConfig()
        assert cfg.fix_build_model == DEFAULT_MODEL

    def test_judge_uses_explicit_value(self):
        cfg = ModelConfig(default="openai:gpt-4", judge="anthropic:claude-3")
        assert cfg.judge_model == "anthropic:claude-3"

    def test_judge_falls_back_to_default(self):
        cfg = ModelConfig(default="openai:gpt-4")
        assert cfg.judge_model == "openai:gpt-4"

    def test_all_fallback_to_module_default(self):
        cfg = ModelConfig()
        assert cfg.analyst_model == DEFAULT_MODEL
        assert cfg.builder_model == DEFAULT_MODEL
        assert cfg.fix_build_model == DEFAULT_MODEL
        assert cfg.judge_model == DEFAULT_MODEL


# ── results.py ────────────────────────────────────────────────────────────────


class TestPipelineResult:
    def test_deployed_url_returns_none_when_no_deploy(self):
        r = PipelineResult(terminal_state=TerminalState.SUCCESS, name="test")
        assert r.deployed_url is None

    def test_deployed_url_from_deploy(self):
        deploy = DeployOutcome(deployed=True, url="https://example.com")
        r = PipelineResult(
            terminal_state=TerminalState.SUCCESS,
            name="test",
            deploy=deploy,
        )
        assert r.deployed_url == "https://example.com"

    def test_terminal_state_enum_values(self):
        assert TerminalState.SUCCESS.value == "success"
        assert TerminalState.DEPLOYED_WITH_GAPS.value == "deployed_with_gaps"
        assert TerminalState.BUILD_FAILED.value == "build_failed"
        assert TerminalState.DEPLOY_FAILED.value == "deploy_failed"


class TestBuildVerifyOutcome:
    def test_deployable_when_built(self):
        bv = BuildVerifyOutcome(
            built=True, matched=True, visual_attempts_used=0, build_attempts_used=0
        )
        assert bv.deployable

    def test_not_deployable_when_not_built(self):
        bv = BuildVerifyOutcome(
            built=False, matched=False, visual_attempts_used=3, build_attempts_used=3
        )
        assert not bv.deployable

    def test_deployable_even_when_not_matched(self):
        bv = BuildVerifyOutcome(
            built=True, matched=False, visual_attempts_used=3, build_attempts_used=0
        )
        assert bv.deployable


class TestDeployOutcome:
    def test_default_message_is_none(self):
        d = DeployOutcome(deployed=True)
        assert d.message is None

    def test_failed_deploy(self):
        d = DeployOutcome(deployed=False, message="auth error")
        assert not d.deployed
        assert d.message == "auth error"


# ── capture.py (signature / mock tests only — needs real Playwright) ──────────


class TestCaptureSignature:
    """Smoke tests: verify the functions exist and accept the right signatures.

    Full tests require a running Playwright browser and are covered by e2e.
    """

    def test_capture_page_async_is_callable(self):
        from pipeline.core.capture import capture_page_async

        sig = inspect.signature(capture_page_async)
        assert "url" in sig.parameters
        assert "viewport_width" in sig.parameters
        assert "viewport_height" in sig.parameters

    def test_capture_page_is_callable(self):
        from pipeline.core.capture import capture_page

        sig = inspect.signature(capture_page)
        assert "url" in sig.parameters
        assert "viewport_width" in sig.parameters
        assert "viewport_height" in sig.parameters
