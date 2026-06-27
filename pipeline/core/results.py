"""Pipeline result and terminal-state types.

The pipeline distinguishes three terminal states (see spec
``pipeline-orchestration`` → "Distinct terminal states"):

- ``SUCCESS``         — the judge reported a visual match within budget.
- ``DEPLOYED_WITH_GAPS`` — visual budget exhausted but the app builds; the best
                        attempt is deployed with a gaps report.
- ``BUILD_FAILED``    — the app could not be built within the build-fix budget;
                        the pipeline hard-stops and does NOT deploy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TerminalState(StrEnum):
    SUCCESS = "success"
    DEPLOYED_WITH_GAPS = "deployed_with_gaps"
    BUILD_FAILED = "build_failed"
    DEPLOY_FAILED = "deploy_failed"


@dataclass
class BuildVerifyOutcome:
    """Result of the builder/verifier stage."""

    built: bool
    matched: bool
    visual_attempts_used: int
    build_attempts_used: int
    similarity: float | None = None
    discrepancies: list[dict] = field(default_factory=list)
    gaps_report_path: str | None = None

    @property
    def deployable(self) -> bool:
        """The app may be deployed iff it builds (matched or not)."""
        return self.built


@dataclass
class DeployOutcome:
    """Result of the deployer stage."""

    deployed: bool
    url: str | None = None
    site_id: str | None = None
    message: str | None = None


@dataclass
class PipelineResult:
    """Final result of a full pipeline run."""

    terminal_state: TerminalState
    name: str
    build_verify: BuildVerifyOutcome | None = None
    deploy: DeployOutcome | None = None
    message: str | None = None

    @property
    def deployed_url(self) -> str | None:
        return self.deploy.url if self.deploy else None
