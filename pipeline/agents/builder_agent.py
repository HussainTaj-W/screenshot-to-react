"""LLM agents used inside the verify loop: code generation and the vision judge.

- The **builder agent** writes/patches ``src/App.jsx`` and ``src/index.css`` from
  the requirements (and, on fixes, from judge discrepancies + its own last
  screenshot).
- The **judge agent** compares the built screenshot to the reference and returns
  a structured ``VisualVerdict``. It is history-aware via ``message_history`` and
  trims image history via ``ProcessHistory``.
- The **fix-build agent** repairs compile errors from build output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent

DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"


# --------------------------------------------------------------------------- #
# Builder (code generation) — produces the two source files
# --------------------------------------------------------------------------- #


class GeneratedApp(BaseModel):
    """The generated React source files."""

    app_jsx: str = Field(description="Full contents of src/App.jsx (a default-export React component).")
    index_css: str = Field(
        description="Full contents of src/index.css (must start with `@import \"tailwindcss\";`)."
    )


BUILDER_INSTRUCTIONS = """\
You are an expert React + Tailwind v4 engineer. You generate a single-page
landing page as two files: src/App.jsx (a default-export function component) and
src/index.css (which MUST begin with `@import "tailwindcss";`).

Follow best practices: semantic HTML, accessible markup, responsive design with
Tailwind breakpoints. Honor the provided requirements exactly, including the
conflict resolutions, fidelity-vs-accessibility rulings, and the documented
responsive assumptions.

Map the DESIGN TOKENS (colors, spacing, type scale, radii, fonts) into a Tailwind
v4 `@theme { ... }` block in src/index.css using CSS custom properties (e.g.
`--color-primary`, `--font-sans`, `--text-2xl`), then use those tokens via
Tailwind utility classes in App.jsx. Use the CONTENT blocks verbatim for copy,
CTAs, and links.

IMAGES — do your best to fill every image slot, in this preference order:
1. A user-SUPPLIED real asset for the slot (see AVAILABLE ASSETS / manifest):
   use it by its public path (e.g. "/hero.png"). Always prefer these.
2. Otherwise, the generated PLACEHOLDER file for the slot, by its public path.
   Placeholders are correctly-sized intentional stand-ins; the user replaces
   them later with real assets at the SAME filename, so use the given names.
3. Only if no provided asset fits a slot, you MAY use an external image URL.

ICONS — use the `lucide-react` library (already installed). Import icons from it
(e.g. `import { ShoppingCart, ChevronDown, ChevronLeft, ChevronRight, Plus,
Star, ArrowRight, Search, Facebook, Twitter, Instagram } from 'lucide-react'`)
and render them as components. Reproduce EVERY icon visible in the reference —
the cart icon (with its notification badge), nav dropdown chevrons, product
carousel left/right arrows, the round "+" add buttons, star ratings, the
"more info" arrows, social icons in the footer, and any small overlay controls
on the hero. Do NOT replace icons with plain text (e.g. don't write the word
"Cart" where the reference shows a cart icon). Hand-drawn inline SVG is allowed
only for a brand logo/wordmark that lucide does not provide.

Output ONLY the two file contents via the structured schema.
"""

FIX_BUILD_INSTRUCTIONS = """\
You are fixing a build/compile error in a Vite + React + Tailwind project. You
are given the current src/App.jsx and src/index.css plus the build error output.
Return corrected, complete contents for BOTH files so the project compiles.
Change only what is necessary to fix the error.
"""


def build_builder_agent(model: str | None = None, **kwargs) -> Agent[None, GeneratedApp]:
    return Agent(
        model or DEFAULT_MODEL,
        output_type=GeneratedApp,
        instructions=BUILDER_INSTRUCTIONS,
        **kwargs,
    )


def build_fix_build_agent(model: str | None = None) -> Agent[None, GeneratedApp]:
    return Agent(
        model or DEFAULT_MODEL,
        output_type=GeneratedApp,
        instructions=FIX_BUILD_INSTRUCTIONS,
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
