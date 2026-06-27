## 1. Project setup & dependencies

- [x] 1.1 Initialize the project with `uv init` and create the pipeline package skeleton under `harness/` (e.g. `pipeline/` with `__init__.py`)
- [x] 1.2 Add dependencies via `uv add`: `pydantic-ai` (+ provider/vision extras), `pydantic-graph`, `pydantic-ai-skills`
- [x] 1.3 `uv add` Playwright and install browser binaries (`uv run playwright install`); verify headless launch works
- [x] 1.4 Verify the Vite + React + Tailwind toolchain is available for generated output
- [x] 1.5 Verify Netlify CLI availability and document `NETLIFY_AUTH_TOKEN` requirement
- [x] 1.6 Confirm all pipeline commands/scripts run via `uv run` (no direct pip/venv usage)

## 2. Shared deps & orchestration scaffold

- [x] 2.1 Define `PipelineDeps` (input paths, reference screenshot, workdir, requirements dir, inferred viewport width, build_cap, visual_cap)
- [x] 2.2 Implement input resolution from the `input/` convention and `--name` -> sibling output dir
- [x] 2.3 Implement the deterministic top-level sequence (analyst -> builder -> deployer) in plain Python
- [x] 2.4 Implement terminal-state handling (hard-stop on build failure; deploy-with-gaps on visual exhaustion; success)
- [x] 2.4a Add a deploy-failure terminal state (built but deploy failed) with non-zero exit
- [x] 2.4b Per-stage model config (`ModelConfig`) read from `PIPELINE_MODEL*` env with fallback chain
- [x] 2.4c Resolve input/path args from `PIPELINE_*` env vars as defaults (CLI flags override)
- [x] 2.4d Progress logging across stages and the build/verify loop
- [x] 2.4e Report runtime skill usage (which skill tools the builder invoked)
- [x] 2.5 Implement toolchain preflight: detect Node.js (min version), Vite/React/Tailwind toolchain, Playwright browsers, and Netlify CLI
- [x] 2.6 Auto-install safe (npm-based) tools when missing: `netlify-cli`, Playwright browsers
- [x] 2.7 Fail loudly with actionable messages for missing system-level tools (e.g. Node.js); never attempt privileged installs
- [x] 2.8 Run the preflight before the analyst/builder/deployer stages; pass through without installs when already satisfied

## 3. Analyst agent (requirements-analysis)

- [x] 3.1 Create the analyst agent with multimodal (vision+text) input of instructions + screenshot
- [x] 3.2 Implement conflict reconciliation (instructions override screenshot) and record conflicts
- [x] 3.3 Implement viewport-width inference and record it
- [x] 3.3a Override the inferred capture width with the screenshot's actual pixel width when they diverge
- [x] 3.4 Implement the assumption ledger (stamp non-evidenced inferences as `ASSUMED`)
- [x] 3.5 Implement fidelity-vs-accessibility per-case rulings in requirements
- [x] 3.6 Implement asset cataloging + extraction (crop/recreate/placeholder) saving files to `<name>/requirements/assets/`
- [x] 3.6a Use normalized 0–1 crop coordinates; extractor scales to the screenshot's actual pixel dimensions
- [x] 3.6b Drop screenshot cropping; generate correctly-sized placeholder images (recreate as SVG/CSS or labeled stand-in PNG) the user can replace later
- [x] 3.6c Identify the reference screenshot by reserved name (screenshot/landingpage/reference); treat other references/ images as supplied assets
- [x] 3.6d Pass supplied asset images+names to the analyst, copy them into the output assets, and map them to slots (strategy `supplied`, no placeholder)
- [x] 3.7 Create the output project dir and write the requirements set (`functional`, `visual`, `non-functional`, `responsive`, `assumptions`, `constraints`, `assets` manifest)
- [x] 3.8 Capture structured design tokens (named colors, spacing/type scales, radii) and write `design-tokens.md`; builder maps them to Tailwind `@theme`
- [x] 3.9 Record page copy/CTAs/links in a dedicated `content.md` separate from layout/behavior

## 4. Builder/Verifier graph (react-build-verify)

- [x] 4.1 Define the `pydantic_graph` state (workdir, requirements, reference shot, viewport, build/visual counters, last build shot, verdict history)
- [x] 4.2 Implement the build node: scaffold/patch the Vite+React+Tailwind app from requirements; import extracted assets
- [x] 4.3 Implement the build-success contract: FIX_BUILD loop with its own global `build_cap`; hard-stop when exhausted
- [x] 4.4 Implement the advisory quality node (eslint + axe) that records findings without looping/blocking
- [x] 4.5 Implement the preview node: start preview server, poll-until-ready, Playwright capture at inferred viewport
- [x] 4.6 Define `VisualVerdict` (matches, similarity, discrepancies[region, issue, severity]) structured output
- [x] 4.7 Implement the vision judge node: history-aware via `message_history`, image history trimmed via `ProcessHistory`
- [x] 4.8 Implement the fix loop: builder receives reference + discrepancies + own last screenshot; "only flagged regions" prompt contract; `visual_cap=3`
- [x] 4.9 Implement exit conditions: match (`similarity>=T`, independent of the judge's boolean so placeholders don't block) -> success; budget exhausted -> emit `gaps_report.md`
- [x] 4.9a Instruct the judge to treat placeholders as expected (no discrepancy/similarity penalty); filter pure placeholder complaints out of the builder's fix instructions and tell it to keep placeholders
- [x] 4.9b Add lucide-react to the scaffold; analyst enumerates visible icons; builder renders icons via the library instead of text substitutes
- [x] 4.10 Wire judge similarity threshold `T` as configuration

## 5. Deployer agent (netlify-deploy)

- [x] 5.1 Implement fresh `dist/` build immediately before deploy
- [x] 5.2 Require `NETLIFY_AUTH_TOKEN`; fail loudly with a clear message when missing
- [x] 5.3 Implement idempotent deploy (reuse site id if present; create + persist id otherwise)
- [x] 5.4 Deploy best attempt + surface gaps report; refuse to deploy only when the app does not build

## 6. Runtime skills integration

- [x] 6.1 Mount `harness/.agents/skills/` on the builder agent via `SkillsCapability` (run_skill_script enabled)
- [x] 6.2 Confirm progressive disclosure works (L1 metadata, L2 load_skill, L3 read_skill_resource) for React/Tailwind/a11y/Playwright/Netlify

## 7. Testing & verification

- [x] 7.1 Unit-test the analyst with `TestModel`/`FunctionModel` (deterministic requirements output)
- [x] 7.2 Unit-test the verify graph state transitions and budget exhaustion paths
- [x] 7.3 Test deployer auth-missing and idempotency branches (mock Netlify)
- [x] 7.4 End-to-end smoke test on a sample instructions file + screenshot through to a local build (no deploy)
- [x] 7.5 Verify the three terminal states (build hard-stop, deploy-with-gaps, success) behave as specified
