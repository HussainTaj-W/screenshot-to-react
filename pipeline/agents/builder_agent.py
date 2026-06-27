"""LLM agents used inside the verify loop: the coding agent and the judges.

- The **builder agent** is a coding agent: it has FileSystem tools and writes /
  edits files directly in the project directory (no fixed output schema), so it
  can structure the app into as many component files as it wants.
- The **judge agent** compares the built screenshot to the reference and returns
  a structured ``VisualVerdict``. It is history-aware via ``message_history`` and
  trims image history via ``ProcessHistory``.
- The **fix-build agent** is also a coding agent that repairs compile errors by
  editing the project files in place.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, BinaryContent

DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"


# --------------------------------------------------------------------------- #
# Builder (coding agent) — writes/edits files directly in the project
# --------------------------------------------------------------------------- #


BUILDER_INSTRUCTIONS = """\
You are an expert React + Tailwind v4 engineer working as a coding agent inside a
Vite project. You have file tools (read_file, write_file, edit_file,
list_directory) scoped to the project root. Use them to build the landing page
directly — there is no fixed output format; structure the code however a senior
engineer would.

Project facts:
- It is a Vite + React 18 + Tailwind v4 project. lucide-react is installed.
- The entry is src/main.jsx which imports './index.css' and './App.jsx'.
- src/App.jsx MUST exist and default-export the root component composing the page.
- src/index.css MUST exist and begin with `@import "tailwindcss";`.
- You MAY (and should) split the UI into multiple component files under
  src/components/ (e.g. Hero.jsx, ProductCard.jsx, Footer.jsx) and import them.
  Prefer well-decomposed, reusable components over one giant file.

Before writing code, load the best-practice skills and apply them: call
load_skill for "vercel-react-best-practices", "tailwind-design-system",
"frontend-design", and "fixing-accessibility". Follow their React, Tailwind,
design, and accessibility guidance.

Honor the provided requirements exactly: functional sections, content/copy,
design tokens, conflict resolutions, fidelity-vs-accessibility rulings, and the
documented responsive assumptions. Map the DESIGN TOKENS (colors, spacing, type
scale, radii, fonts) into a Tailwind v4 `@theme { ... }` block in src/index.css,
then use those tokens via Tailwind utility classes. Build a responsive layout
with Tailwind breakpoints, semantic HTML, and accessible markup.

IMAGES — fill every image slot, in this preference order:
1. A user-SUPPLIED real asset for the slot (see AVAILABLE ASSETS / manifest):
   reference it by its public path (e.g. "/hero.png"). Always prefer these.
2. Otherwise, the generated PLACEHOLDER file for the slot, by its public path.
   Placeholders are correctly-sized intentional stand-ins; the user replaces
   them later with real assets at the SAME filename, so use the given names.
3. Only if no provided asset fits a slot, you MAY use an external image URL.

ICONS — use the `lucide-react` library. Import icons (e.g. ShoppingCart,
ChevronDown, ChevronLeft, ChevronRight, Plus, Star, ArrowRight, Search, Facebook,
Twitter, Instagram) and render them as components. Reproduce EVERY icon visible
in the reference (cart with badge, nav chevrons, carousel arrows, round "+" add
buttons, star ratings, "more info" arrows, footer social icons, hero overlay
controls). Do NOT substitute plain text for an icon. Inline SVG only for a brand
logo/wordmark lucide lacks.

When you have written all the files, reply with a brief one-line summary.
"""

FIX_BUILD_INSTRUCTIONS = """\
You are a coding agent fixing a build/compile error in a Vite + React + Tailwind
project. You have file tools (read_file, write_file, edit_file, list_directory)
scoped to the project root. Read the relevant files, fix the cause of the error,
and write the corrected files. Change only what is necessary to make the project
compile. Reply with a one-line summary when done.
"""


def build_builder_agent(
    model: str | None = None,
    *,
    workdir: Path | None = None,
    capabilities: list | None = None,
):
    """Construct the builder coding agent with FileSystem tools scoped to workdir."""
    from pydantic_ai_harness.filesystem import FileSystem

    caps = list(capabilities or [])
    if workdir is not None:
        caps.append(FileSystem(root_dir=workdir))
    return Agent(
        model or DEFAULT_MODEL,
        instructions=BUILDER_INSTRUCTIONS,
        capabilities=caps,
    )


def build_fix_build_agent(model: str | None = None, *, workdir: Path | None = None):
    """Construct the fix-build coding agent with FileSystem tools."""
    from pydantic_ai_harness.filesystem import FileSystem

    caps = []
    if workdir is not None:
        caps.append(FileSystem(root_dir=workdir))
    return Agent(
        model or DEFAULT_MODEL,
        instructions=FIX_BUILD_INSTRUCTIONS,
        capabilities=caps,
    )


# --------------------------------------------------------------------------- #
# Judge (vision) — structured verdict, history-aware
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


def build_judge_agent(model: str | None = None):
    """Construct the vision judge with trimmed image history.

    Uses ``ProcessHistory`` to keep the textual verdict trajectory while
    dropping older images so image-token cost does not balloon across attempts.
    """
    from pydantic_ai.capabilities import ProcessHistory
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        UserPromptPart,
    )

    async def trim_images(messages):
        """Keep all text, but strip image BinaryContent from older user turns.

        The most recent user turn (current build + reference) keeps its images;
        older turns keep only their text so the judge retains the reasoning
        trajectory without resending every past screenshot.
        """
        if len(messages) <= 1:
            return messages
        trimmed = list(messages)
        # Strip images from all but the last message.
        for msg in trimmed[:-1]:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                        part.content = [
                            c for c in part.content if not isinstance(c, BinaryContent)
                        ]
        return trimmed

    from ..graph.state import VisualVerdict

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


def build_responsive_judge_agent(model: str | None = None):
    """Construct the mobile responsive sanity judge (no reference image)."""
    from ..graph.state import ResponsiveVerdict

    return Agent(
        model or DEFAULT_MODEL,
        output_type=ResponsiveVerdict,
        instructions=RESPONSIVE_JUDGE_INSTRUCTIONS,
    )
