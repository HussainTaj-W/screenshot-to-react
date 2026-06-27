## Context

The pipeline turns an instructions file + a single reference screenshot into a deployed, responsive React landing page. It is greenfield: the `harness/` repo currently contains only OpenSpec config and installed skills. The work spans three LLM-driven agents, a stateful verify loop, a headless-browser capture step, and an external deploy target (Netlify) — a cross-cutting change that benefits from settling architecture before coding.

Key constraints:
- The pipeline is a Python project managed with **uv** (`uv add` for dependencies, `uv run` for execution, `pyproject.toml`); pip/poetry/venv are not used directly.
- A single screenshot pins exactly **one viewport at one width**. Fidelity can only be verified there; everything else (responsive breakpoints, hover/focus, below-the-fold) is inferred.
- Vision-based screenshot comparison has no off-the-shelf skill; the judge is custom, built on Pydantic AI multimodal input.
- Pixel-perfect reproduction from one screenshot is inherently imperfect (missing fonts, eyeballed spacing/color, raster assets).

## Goals / Non-Goals

**Goals:**
- Autonomously produce a Vite + React + Tailwind landing page that visually matches the reference at its shown viewport.
- Make every inferred decision auditable via a requirements set + assumption ledger that travels with the output project.
- Guarantee a compiling, deployable app; deploy the best attempt with a gaps report when perfect fidelity isn't reached.
- Keep control flow deterministic; confine LLM usage to judgment/generation, not orchestration.

**Non-Goals:**
- Pixel-perfect fidelity at viewports other than the reference's.
- Judge-verifying responsive behavior, interactions, or code quality (a11y/semantics) the screenshot cannot show.
- Multi-page sites, routing, or backend functionality — single landing page only.
- Building a reusable visual-diff library; the judge is purpose-built for this pipeline.

## Decisions

**1. Deterministic top-level sequence; `pydantic_graph` only for the verify loop.**
The analyst → builder → deployer order never branches, so it is plain Python. The verify loop has real branching, counters, and loops, so it is a `pydantic_graph` state machine. *Alternative considered:* an LLM orchestrator delegating via tools — rejected because it adds non-determinism and token cost to a sequence requiring no decisions. *Alternative:* one graph for the whole pipeline — rejected as ceremony over linear steps.

**2. Vision LLM judge (not pixel diff).** The judge renders the built page, screenshots it via Playwright at the inferred width, and returns a structured `VisualVerdict{matches, similarity, discrepancies[]}`. *Alternative:* pixel diff — rejected as brittle to fonts/anti-aliasing/sub-pixel shifts. Structured output makes the exit condition mechanical and doubles as the gaps report and the builder's work order.

**3. Two budgets, not three.** Build success is a **hard contract** with its own global retry cap (`build_cap`); exhausting it hard-stops the run (a non-compiling app cannot deploy). Visual fixes get `visual_cap=3` (initial build + 3 fixes); exhausting it deploys the best attempt + gaps report. The lint/a11y (axe) gate is **advisory only** — it records findings and never loops or blocks. *Rationale:* the user clarified build success is the invariant and quality checks are "extra steps."

**4. Instructions override the screenshot on conflict;** the analyst records the conflict. The analyst also decides **fidelity-vs-accessibility per case** (e.g. fix low-contrast text even if it diverges) so builder and judge don't fight.

**5. Assumption ledger.** Anything not directly evidenced by the screenshot is stamped `ASSUMED` in the requirements (responsive breakpoints, mobile nav, hover/focus, below-fold). This sharply bounds the judge's scope to the shown viewport and keeps the rebuild honest.

**6. Judge is history-aware, with trimmed images.** Each judge attempt carries the prior verdict trajectory via `message_history`; image tokens are trimmed (keep text verdicts, only the most recent build screenshot) via `ProcessHistory`. *Rationale:* avoids oscillation without ballooning image-token cost.

**7. Builder context = reference + discrepancies + its own last screenshot.** The builder and judge share a visual frame. Anti-regression relies on an explicit "only modify flagged regions" prompt contract, with the 3-attempt budget absorbing residual oscillation.

**8. Filesystem: siblings, scripts run from `top/`.** `harness/` (generator), `input/` (instructions + references), and `<name>/` (the product) are siblings. Requirements + extracted assets live **inside** `<name>/` so the product is self-describing. The analyst creates `<name>/`; the builder populates it; the deployer ships `dist/`.

**9. Runtime skills via `SkillsCapability`.** The builder mounts `harness/.agents/skills/` (verified OpenCode/agentskills.io-compatible format) with `run_skill_script` enabled, exposing React/Tailwind/a11y/Playwright/Netlify guidance through 3-level progressive disclosure. *Alternative:* baking guidance into static instructions — kept as fallback, but `pydantic-ai-skills` gives on-demand loading for free.

## Risks / Trade-offs

- **Pixel-perfect is unattainable from one screenshot** → Define "done" as match-at-shown-viewport + documented assumptions; deploy best attempt + gaps report.
- **Judge false-positive ("matches" when it doesn't)** → Require `matches==true AND similarity≥T`; treat `T` as tunable config.
- **Oscillation (fix A breaks B)** → History-aware judge + "only flagged regions" prompt contract + bounded budget.
- **Stubborn compile error consumes the run** → Separate global `build_cap`; build-fix loops route back to build, never advancing to the judge until compiling.
- **`run_skill_script` executes code from 2 third-party skills** → Skills are plain files, auditable on disk; user accepted the tradeoff; can scope permissions later.
- **Cost/latency (~4–10 model calls + several browser cycles per page)** → Trim judge image history; advisory gate doesn't loop; acceptable for the use case.
- **Unfair comparison if viewport mis-inferred** → Analyst infers and records viewport width; Playwright captures at that exact width.

## Open Questions

- Exact value/calibration of the judge similarity threshold `T` (config, tuned on real runs).
- Precise `gaps_report.md` format/schema.
- Netlify site-id persistence mechanism for idempotent re-runs (config file vs. env).
- Default `build_cap` value.
