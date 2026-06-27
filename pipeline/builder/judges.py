"""Vision judges and their structured verdicts.

- The **visual judge** compares the built screenshot to the reference and returns
  a ``VisualVerdict``. It is history-aware and trims image history.
- The **responsive judge** evaluates a mobile capture on its own merits (no
  reference) and returns a ``ResponsiveVerdict``.

The verdict models live here, alongside the judges that produce them.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent

from ..core.config import DEFAULT_MODEL

# --------------------------------------------------------------------------- #
# Verdict models
# --------------------------------------------------------------------------- #


class Severity(StrEnum):
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
# Visual judge (history-aware, trims image history)
# --------------------------------------------------------------------------- #

JUDGE_INSTRUCTIONS = """\
You are a meticulous visual QA judge. You are given a REFERENCE screenshot and a
screenshot of the CURRENT build. Compare them at the shown viewport ONLY.

Evaluate LAYOUT, color, typography, spacing, structure, and copy. Do NOT penalize
for responsive behavior, interactions, or content that the reference does not
show.

IMPORTANT — PLACEHOLDER IMAGES ARE EXPECTED:
The build intentionally uses neutral gray placeholder images where the real
photos aren't available yet. A gray/blank placeholder in place of a reference
photo is EXPECTED and is NOT a defect. Do NOT lower similarity or raise a
discrepancy merely because an image is a placeholder rather than the real photo.
Judge whether the placeholder is the RIGHT SIZE and in the RIGHT POSITION, not
its visual content. Your similarity score should reflect how well the LAYOUT and
STRUCTURE match, treating correctly-placed placeholders as correct.

Return a structured verdict:
- matches: true if the layout/structure faithfully matches (placeholders OK).
- similarity: your 0..1 estimate of LAYOUT/STRUCTURE fidelity (placeholders that
  are correctly sized/placed count as matching).
- discrepancies: for each REAL difference (wrong layout, spacing, color, copy,
  or a misplaced/mis-sized element), give region, the issue (and the target),
  and a severity. Do NOT create discrepancies that just say "placeholder instead
  of real photo". If an image placeholder is the wrong size or position, that IS
  a valid discrepancy (describe the size/position issue, not the missing photo).

If you have seen prior attempts, account for regressions: a region that was
correct before but is now wrong is a new discrepancy.
"""


def build_judge_agent(model: str | None = None) -> Agent:
    """Construct the vision judge with trimmed image history.

    Uses ``ProcessHistory`` to keep the textual verdict trajectory while
    dropping older images so image-token cost does not balloon across attempts.
    """
    from pydantic_ai.capabilities import ProcessHistory
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    async def trim_images(messages):
        """Keep all text, but strip image content from older user turns.

        The most recent user turn (current build + reference) keeps its images;
        older turns keep only their text so the judge retains the reasoning
        trajectory without resending every past screenshot.
        """
        if len(messages) <= 1:
            return messages
        trimmed = list(messages)
        for msg in trimmed[:-1]:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                        part.content = [c for c in part.content if not isinstance(c, BinaryContent)]
        return trimmed

    return Agent(
        model or DEFAULT_MODEL,
        output_type=VisualVerdict,
        instructions=JUDGE_INSTRUCTIONS,
        capabilities=[ProcessHistory(trim_images)],
    )


# --------------------------------------------------------------------------- #
# Responsive sanity judge (mobile) — no reference, judged on its own merits
# --------------------------------------------------------------------------- #

RESPONSIVE_JUDGE_INSTRUCTIONS = """\
You are a responsive-design QA judge. You are given a screenshot of the build
captured at a MOBILE viewport width. There is NO reference image for this width —
judge the layout ON ITS OWN MERITS for whether it is a sane, usable mobile
layout, plus whether it is consistent with the DOCUMENTED RESPONSIVE ASSUMPTIONS
provided.

Separate OBJECTIVE BREAKAGE from SUGGESTIONS:
- OBJECTIVE BREAKAGE (set broken=true and list under issues): horizontal
  overflow / a horizontal scrollbar, any element or content wider than the
  viewport, text overflowing or clipped out of its container, elements
  overlapping so content is unreadable, or a layout that is clearly shattered.
- SUGGESTIONS (non-blocking improvements; never set broken for these): ONLY
  HIGH-IMPACT improvements to mobile responsiveness OR user experience —
  changes that meaningfully affect usability, readability, or task completion
  (e.g. "tap targets are too small to reliably tap", "primary CTA is below the
  fold and hard to find", "text is too small to read comfortably"). Each
  suggestion has a region and an actionable instruction.

  DO NOT emit low-value or cosmetic nitpicks (minor spacing/padding tweaks,
  slight font-size preferences, "could be a touch more spacious", aesthetic
  opinions). If the mobile layout is already usable and clear, return ZERO
  suggestions. Prefer returning NO suggestions over noisy ones — these go to the
  builder, and trivial suggestions confuse it and cause regressions. Return AT
  MOST 3 suggestions, and only ones you would consider genuinely high impact.

Placeholder gray images are EXPECTED — never treat a placeholder as breakage.

Return:
- broken: true ONLY if there is objective breakage as defined above.
- issues: concrete objective problems to fix (region, issue, severity), only
  when broken.
- suggestions: at most 3 high-impact responsiveness/UX improvements (region +
  suggestion); empty when the layout is already usable and clear.
"""


def build_responsive_judge_agent(model: str | None = None) -> Agent:
    """Construct the mobile responsive sanity judge (no reference image)."""
    return Agent(
        model or DEFAULT_MODEL,
        output_type=ResponsiveVerdict,
        instructions=RESPONSIVE_JUDGE_INSTRUCTIONS,
    )
