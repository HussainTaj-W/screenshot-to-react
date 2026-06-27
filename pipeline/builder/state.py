"""Verify-loop mutable state.

The graph state carries the two budgets' counters, the most recent build
screenshot, and the verdict trajectory used to keep the judge history-aware. The
verdict models themselves live with the judges in ``judges.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .judges import Discrepancy, VisualVerdict


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
