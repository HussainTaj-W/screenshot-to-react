"""Command-line entry point.

Usage:
    uv run screenshot-to-react --name mylanding
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .core.config import ModelConfig
from .core.deps import (
    DEFAULT_SIMILARITY_THRESHOLD,
    InputResolutionError,
    PipelineDeps,
)
from .core.preflight import PreflightError
from .core.results import TerminalState
from .orchestrator import run_pipeline


def _load_env() -> None:
    """Load a .env file (cwd and parents) so provider keys/URLs are available.

    Honors OPENAI_API_KEY / OPENAI_BASE_URL / ANTHROPIC_API_KEY etc. Existing
    environment variables are NOT overridden.
    """
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=False)


def _env_default(*keys: str) -> str | None:
    """Return the first non-empty value among the given env vars, else None."""
    import os

    for k in keys:
        val = os.environ.get(k)
        if val and val.strip():
            return val.strip()
    return None


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="screenshot-to-react",
        description=(
            "Recreate a landing page from a reference screenshot as a deployed "
            "React app. Path args default from PIPELINE_* env vars (see "
            ".env.example); CLI flags override them."
        ),
    )
    p.add_argument(
        "--name",
        default=_env_default("PIPELINE_NAME"),
        help="Output project name (env: PIPELINE_NAME); written to <top>/<name>/.",
    )
    p.add_argument(
        "--top",
        default=_env_default("PIPELINE_TOP"),
        help="Top directory (env: PIPELINE_TOP; default: cwd).",
    )
    p.add_argument(
        "--input-dir",
        default=_env_default("PIPELINE_INPUT_DIR"),
        help="Override the input/ directory (env: PIPELINE_INPUT_DIR).",
    )
    p.add_argument(
        "--instructions",
        default=_env_default("PIPELINE_INSTRUCTIONS"),
        help="Instructions file path (env: PIPELINE_INSTRUCTIONS).",
    )
    p.add_argument(
        "--references-dir",
        default=_env_default("PIPELINE_REFERENCES_DIR"),
        help="References directory (env: PIPELINE_REFERENCES_DIR).",
    )
    p.add_argument(
        "--skills-dir",
        default=_env_default("PIPELINE_SKILLS_DIR"),
        help="Runtime skills directory (env: PIPELINE_SKILLS_DIR; default: <top>/.agents/skills).",
    )
    p.add_argument(
        "--model",
        default=None,
        help=(
            "Global model override (wins over PIPELINE_MODEL env). Per-stage "
            "models are configured via PIPELINE_MODEL_* env vars (see .env.example)."
        ),
    )
    p.add_argument("--build-cap", type=int, default=3, help="Global build-fix budget.")
    p.add_argument("--visual-cap", type=int, default=3, help="Visual fix budget.")
    p.add_argument(
        "--similarity-threshold",
        type=float,
        default=DEFAULT_SIMILARITY_THRESHOLD,
        help="Judge similarity threshold T for a match.",
    )
    p.add_argument(
        "--responsive-width",
        type=int,
        default=int(_env_default("PIPELINE_RESPONSIVE_WIDTH") or 375),
        help="Mobile width for the responsive sanity check (env: PIPELINE_RESPONSIVE_WIDTH).",
    )
    p.add_argument(
        "--no-responsive-check",
        action="store_true",
        help="Disable the mobile responsive sanity check.",
    )
    p.add_argument(
        "--site-id",
        default=_env_default("NETLIFY_SITE_ID"),
        help="Deploy to this existing Netlify site id (env: NETLIFY_SITE_ID). "
        "If unset, reuses a prior deploy's site or creates a new one.",
    )
    p.add_argument(
        "--no-deploy",
        action="store_true",
        help="Run analyst + build/verify only; skip Netlify deployment.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose (DEBUG) logging.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    _load_env()

    # Optionally capture outgoing model requests for debugging provider errors.
    from .core.debug_requests import enable_if_configured

    enable_if_configured()

    args = _build_parser().parse_args(argv)

    import logging

    from .core.logging import configure_logging

    configure_logging(logging.DEBUG if args.verbose else logging.INFO)

    if not args.name:
        print(
            "Error: --name is required (or set PIPELINE_NAME in .env).",
            file=sys.stderr,
        )
        return 2

    # Per-stage models come from the environment (.env); --model overrides the
    # global default.
    models = ModelConfig.from_env()
    if args.model:
        models.default = args.model

    try:
        deps = PipelineDeps.resolve(
            name=args.name,
            top=args.top,
            input_dir=args.input_dir,
            instructions=args.instructions,
            references_dir=args.references_dir,
            skills_dir=args.skills_dir,
            build_cap=args.build_cap,
            visual_cap=args.visual_cap,
            similarity_threshold=args.similarity_threshold,
            responsive_width=args.responsive_width,
            check_responsive=not args.no_responsive_check,
            netlify_site_id=args.site_id,
            models=models,
        )
    except InputResolutionError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(run_pipeline(deps, deploy=not args.no_deploy))
    except PreflightError as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        return 3

    print(f"\nTerminal state: {result.terminal_state.value}")
    if result.message:
        print(result.message)
    if result.deployed_url:
        print(f"Deployed: {result.deployed_url}")

    # Non-zero exit only on hard build failure.
    failed = {TerminalState.BUILD_FAILED, TerminalState.DEPLOY_FAILED}
    return 1 if result.terminal_state in failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
