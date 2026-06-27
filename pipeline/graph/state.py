"""Verify-loop state and the judge's structured verdict.

The graph state carries the two budgets' counters, the most recent build
screenshot, and the verdict trajectory used to keep the judge history-aware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Judge verdict (task 4.6)
# --------------------------------------------------------------------------- #


class Severity(str, Enum):
    MINOR = "minor"
    MAJOR = "major"
    BLOCKER = "blocker"


class Discrepancy(BaseModel):
    region: str = Field(description="Where on the page, e.g. 'hero headline'.")
    issue: str = Field(description="What is wrong and the target, e.g. 'too light → bold'.")
    severity: Severity = Severity.MAJOR


class VisualVerdict(BaseModel):
    """The vision judge's structured output.

    Serves triple duty: exit condition, builder work-order, and gaps report.
    """

    matches: bool = Field(description="True only if the build matches the reference.")
    similarity: float = Field(
        ge=0.0, le=1.0, description="The judge's own 0..1 similarity estimate."
    )
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    notes: str = Field(default="", description="Optional reasoning summary.")


class ResponsiveSuggestion(BaseModel):
    """A non-blocking improvement suggestion for the mobile layout."""

    region: str = Field(description="Where, e.g. 'hero', 'product grid', 'footer'.")
    suggestion: str = Field(description="A concrete, actionable improvement.")


class ResponsiveVerdict(BaseModel):
    """The responsive sanity judge's output for a mobile capture.

    There is no reference for non-reference viewports, so this judges the page
    on its own merits. ``broken`` is the objective signal (overflow / elements
    wider than the viewport / overlap / clipping); ``issues`` are the concrete
    objective problems to fix; ``suggestions`` are non-blocking improvements.
    """

    broken: bool = Field(
        description="True if the mobile layout has OBJECTIVE breakage (overflow, "
        "elements wider than the viewport, overlapping or clipped content)."
    )
    issues: list[Discrepancy] = Field(
        default_factory=list,
        description="Objective breakage to fix (only when broken).",
    )
    suggestions: list[ResponsiveSuggestion] = Field(
        default_factory=list,
        description="Non-blocking improvement suggestions for the mobile layout.",
    )


# --------------------------------------------------------------------------- #
# Graph state (task 4.1)
# --------------------------------------------------------------------------- #


@dataclass
class VerifyState:
    """Mutable state threaded through the verify graph.

    Budgets are global across the whole run (design.md decision 3).
    """

    # counters
    build_attempts: int = 0  # build-fix attempts used
    visual_attempts: int = 0  # visual-fix attempts used (initial build not counted)

    # caps (copied from deps for convenience)
    build_cap: int = 3
    visual_cap: int = 3
    similarity_threshold: float = 0.95

    # latest artifacts
    last_build_succeeded: bool = False
    last_build_error: str | None = None
    last_build_shot: bytes | None = None  # most recent build screenshot (PNG)

    # judge trajectory (text verdicts kept; image history trimmed)
    verdict_history: list[VisualVerdict] = field(default_factory=list)

    # objective mobile-responsive breakage from the latest attempt
    last_responsive_issues: list[Discrepancy] = field(default_factory=list)

    # non-blocking responsive suggestions from the latest attempt
    last_responsive_suggestions: list = field(default_factory=list)

    # advisory quality findings (non-blocking)
    quality_findings: list[str] = field(default_factory=list)

    # terminal flags
    matched: bool = False
    build_failed: bool = False

    @property
    def latest_verdict(self) -> VisualVerdict | None:
        return self.verdict_history[-1] if self.verdict_history else None
