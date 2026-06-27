"""Builder coding agents (no fixed output schema).

The builder and fix-build agents have FileSystem tools and write/edit files
directly in the project directory, so they can structure the app into as many
component files as they want and edit incrementally on fix passes.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent

from ..core.config import DEFAULT_MODEL

BUILDER_INSTRUCTIONS = """\
You are an expert React + Tailwind v4 engineer working as a coding agent inside a
Vite project. You have file tools (read_file, write_file, edit_file,
list_directory) scoped to the project root. Use them to build the landing page
directly — there is no fixed output format; structure the code however a senior
engineer would.

Project facts:
- It is a Vite + React 19 + Tailwind v4 project. lucide-react is installed.
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
) -> Agent:
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


def build_fix_build_agent(model: str | None = None, *, workdir: Path | None = None) -> Agent:
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
