"""Per-stage model selection configuration.

``ModelConfig`` chooses which LLM model each pipeline stage uses, with a global
default and per-stage overrides, all configurable from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Default model used when no per-stage or global override is given.
DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"


@dataclass
class ModelConfig:
    """Per-stage model selection with a fallback chain.

    Resolution order for each stage: explicit per-stage value -> global
    ``default`` -> module ``DEFAULT_MODEL``. ``None`` means "fall back".

    Configured via environment (typically a ``.env`` file):

        PIPELINE_MODEL            global default for all stages
        PIPELINE_MODEL_ANALYST    analyst (vision + reasoning)
        PIPELINE_MODEL_BUILDER    code generation
        PIPELINE_MODEL_FIX_BUILD  compile-error fixing (cheap)
        PIPELINE_MODEL_JUDGE      vision judge
    """

    default: str | None = None  # global override
    analyst: str | None = None  # vision + reasoning
    builder: str | None = None  # code generation
    fix_build: str | None = None  # cheap, narrow compile-error fixing
    judge: str | None = None  # vision discrimination

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ModelConfig:
        """Build a config from environment variables (empty values ignored)."""
        src = env if env is not None else os.environ

        def get(key: str) -> str | None:
            val = src.get(key)
            return val.strip() if val and val.strip() else None

        return cls(
            default=get("PIPELINE_MODEL"),
            analyst=get("PIPELINE_MODEL_ANALYST"),
            builder=get("PIPELINE_MODEL_BUILDER"),
            fix_build=get("PIPELINE_MODEL_FIX_BUILD"),
            judge=get("PIPELINE_MODEL_JUDGE"),
        )

    def _resolve(self, stage: str | None) -> str:
        return stage or self.default or DEFAULT_MODEL

    @property
    def analyst_model(self) -> str:
        return self._resolve(self.analyst)

    @property
    def builder_model(self) -> str:
        return self._resolve(self.builder)

    @property
    def fix_build_model(self) -> str:
        # fix_build falls back to builder before the global default.
        return self.fix_build or self.builder or self.default or DEFAULT_MODEL

    @property
    def judge_model(self) -> str:
        return self._resolve(self.judge)
