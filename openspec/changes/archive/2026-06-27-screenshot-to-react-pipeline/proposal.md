## Why

Recreating a landing page from a reference screenshot is repetitive, error-prone manual work: a developer reads the screenshot, hand-writes React, eyeballs the result, fixes discrepancies, and deploys. This change introduces an autonomous, three-agent pipeline that takes an instructions file plus a reference screenshot and produces a deployed, responsive React landing page — verifying fidelity against the reference automatically and capturing every inferred decision as an auditable record.

## What Changes

- A new agentic pipeline (Pydantic AI) that takes `input/instructions.md` + `input/references/<screenshot>` and produces a deployed landing page at a Netlify URL, named via a `--name` parameter (output written to a sibling `<name>/` directory).
- **Analyst agent**: reads instructions (text) + screenshot (vision), reconciles conflicts (instructions override the screenshot), infers the reference viewport width, and writes an auditable requirements set into `<name>/requirements/` — including an explicit **assumption ledger** stamping every inference not directly evidenced by the screenshot (responsive breakpoints, hover/focus states, below-the-fold content). Catalogs and **extracts** assets (crop from screenshot, recreate in CSS/SVG, or placeholder).
- **Builder/Verifier agent**: a `pydantic_graph` state machine that scaffolds a Vite + React + Tailwind app, enforces a hard **build-success contract**, runs an **advisory** lint/a11y (axe) pass, captures a Playwright screenshot at the inferred viewport, and runs a **vision LLM judge** that returns a structured verdict. Loops to fix flagged discrepancies up to a budget of 3 visual attempts (initial build + 3 fixes).
- **Deployer agent**: builds a fresh `dist/`, deploys to Netlify (idempotent via reused site id), and ships the best attempt plus a gaps report when the visual budget is exhausted.
- **Orchestration**: a deterministic top-level Python sequence (analyst → builder → deployer) — no LLM drives control flow — with the only branching/looping living inside the builder's verify graph.
- Adds the `pydantic-ai-skills` dependency so the builder agent mounts the installed best-practice skills (React, Tailwind, a11y, Playwright, Netlify) via `SkillsCapability` for runtime progressive disclosure.

## Capabilities

### New Capabilities

- `requirements-analysis`: Vision+text analysis of the screenshot and instructions into an auditable requirements set, conflict reconciliation, viewport inference, asset extraction/cataloging, and the assumption ledger.
- `react-build-verify`: The Vite+React+Tailwind build, the build-success contract, advisory lint/a11y gate, Playwright capture, vision-judge comparison, structured verdict, and the bounded fix loop.
- `netlify-deploy`: Fresh build, idempotent Netlify deployment, and best-attempt + gaps-report deployment on visual-budget exhaustion.
- `pipeline-orchestration`: The deterministic top-level sequencing of the three agents, shared `PipelineDeps` (paths, viewport, budgets), filesystem conventions (`input/`, sibling `<name>/` output), and terminal-state handling (hard-stop on build failure vs. deploy-with-gaps on visual exhaustion).

### Modified Capabilities

<!-- None. This is a greenfield pipeline; no existing specs change. -->

## Impact

- **New code**: Pipeline package under `harness/` (analyst, builder graph, deployer, orchestrator, `PipelineDeps`).
- **New dependencies**: `pydantic-ai` (+slim extras), `pydantic-ai-skills`, `pydantic-graph`, Playwright (browsers), Vite/React/Tailwind toolchain (for generated output), Netlify CLI.
- **Generated artifacts**: A sibling `<name>/` project directory (React app + `requirements/` + extracted assets + `dist/`).
- **External systems**: Netlify (requires `NETLIFY_AUTH_TOKEN`); a vision-capable LLM provider for the analyst and judge.
- **Skills**: Consumes the 8 skills installed in `harness/.agents/skills/` at authoring time and (the 6 web/deploy ones) at runtime via `SkillsCapability`.
- **Scope/known limits**: Fidelity is verified only at the single reference viewport; responsive behavior at other widths is assumption-driven and documented, not judge-verified. No off-the-shelf skill covers vision-based screenshot diffing — the judge is custom.
