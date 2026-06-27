# screenshot-to-react

An agentic pipeline that takes an **instructions file** plus a **reference
landing-page screenshot** and produces a **deployed, responsive React landing
page**. It runs three stages in a fixed, deterministic order:

1. **Analyst** — vision+text analysis of the screenshot and instructions into an
   auditable requirements set (assumption ledger, design tokens, content, and an
   asset manifest). Has read-only file tools to discover extra reference files.
2. **Builder/Verifier** — a `pydantic_graph` state machine driving a **coding
   agent** (with filesystem tools) that scaffolds a Vite + React + Tailwind app
   and writes/edits the source files directly, decomposing the UI into multiple
   components. It enforces a build-success contract and iterates on:
   - **visual fidelity** — a vision judge compares the build to the reference;
   - **mobile responsiveness** — a separate judge checks a mobile capture for
     objective breakage (no reference exists for other viewports).
3. **Deployer** — builds a fresh `dist/` and deploys to Netlify (idempotently).

## Requirements

### Python (managed with uv)

This is a Python project managed entirely with [uv](https://docs.astral.sh/uv/).
Use `uv add` for dependencies and `uv run` to execute commands — do not use
pip/poetry/venv directly.

```bash
uv sync                              # install dependencies
uv run playwright install chromium   # one-time browser install
```

### System toolchain (for the generated app)

The generated landing page is a Node/Vite project, so the following must be
available. The pipeline performs a runtime **toolchain preflight** that
auto-installs npm-based tools when missing and fails loudly for system-level
tools:

| Tool                | Minimum | Provisioning                                |
| ------------------- | ------- | ------------------------------------------- |
| Node.js             | 18.14+  | **system-level** — fail loud if missing     |
| npm / npx           | bundled | with Node.js                                |
| Playwright          | —       | `uv run playwright install chromium`        |
| Vite/React/Tailwind | —       | scaffolded per-run via `npm create vite`    |
| Netlify CLI         | —       | auto-installed via `npx`/`npm` when missing |

## Configuration

Configuration is read from the environment (typically a `.env` file — see
`.env.example`). CLI flags override env vars.

### Required

| Variable             | Required for  | Purpose                                       |
| -------------------- | ------------- | --------------------------------------------- |
| LLM provider key     | all LLM calls | e.g. `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`.  |
| `NETLIFY_AUTH_TOKEN` | deploy        | Netlify auth (CI-style, no browser).          |

The analyst, builder, and both judges send images, so the model(s) must be
**vision-capable**. `NETLIFY_AUTH_TOKEN` is required for the deploy stage; the
deployer fails loudly with an actionable message when it is missing.

### Models (per stage)

| Variable                   | Stage                          |
| -------------------------- | ------------------------------ |
| `PIPELINE_MODEL`           | global default for all stages  |
| `PIPELINE_MODEL_ANALYST`   | analyst (vision + reasoning)   |
| `PIPELINE_MODEL_BUILDER`   | code generation                |
| `PIPELINE_MODEL_FIX_BUILD` | compile-error fixing (cheap)   |
| `PIPELINE_MODEL_JUDGE`     | the vision/responsive judges   |

Each stage falls back to `PIPELINE_MODEL` when its override is unset. Use a
`provider:model` string, e.g. `openai:gemini-3.5-flash`. `--model` overrides the
global default.

### Paths and options (env or flags)

| Variable / flag                          | Purpose                                   |
| ---------------------------------------- | ----------------------------------------- |
| `PIPELINE_NAME` / `--name`               | output project name (required)            |
| `PIPELINE_TOP` / `--top`                 | top directory (default: cwd)              |
| `PIPELINE_INSTRUCTIONS` / `--instructions` | instructions file path                  |
| `PIPELINE_REFERENCES_DIR` / `--references-dir` | references directory                |
| `PIPELINE_SKILLS_DIR` / `--skills-dir`   | runtime skills (default: `.agents/skills`)|
| `PIPELINE_RESPONSIVE_WIDTH` / `--responsive-width` | mobile width (default 375)      |
| `NETLIFY_SITE_ID` / `--site-id`          | deploy to an existing Netlify site        |
| `--build-cap`, `--visual-cap`            | fix budgets                               |
| `--similarity-threshold`                 | match threshold T (default 0.9)           |
| `--no-responsive-check`                  | disable the mobile responsive check       |
| `--no-deploy`                            | run analyst + build/verify only           |
| `-v` / `--verbose`                       | DEBUG logging                             |

## Usage

```bash
uv run screenshot-to-react --name mylanding
```

With `.env` configured (paths + models), it can be as short as:

```bash
uv run screenshot-to-react
```

### Docker / Podman

A `Dockerfile` bundles everything (Python + uv, Node, Playwright Chromium;
Netlify CLI is auto-installed at runtime). Build once, then mount the project
tree so inputs, outputs, `.env`, and skills come from the host:

```bash
podman build -t screenshot-to-react .

# Mount the parent project dir (which holds harness/, input/, and the output)
# and run from harness/ so the PIPELINE_* relative paths resolve as on the host:
podman run --rm \
  -v "$PWD/..":/work \
  --workdir /work/harness \
  screenshot-to-react
```

Pass flags after the image name (e.g. `... screenshot-to-react --no-deploy -v`),
or configure everything via the mounted `.env`. (`docker` works identically.)

### Inputs

Inputs follow the `input/` convention. The reference screenshot is identified by
a reserved base name (`screenshot.*`, `landingpage.*`, or `reference.*`); any
**other** image in the references directory is treated as a supplied asset that
the builder uses in place of a generated placeholder.

```
input/
├── instructions.md
└── references/
    ├── landingpage.png      # the reference screenshot (reserved name)
    └── hero.png             # optional supplied asset(s)
```

### Output

Output is written to a sibling project directory named by `--name`:

```
<name>/
├── requirements/      # analyst output (+ extracted assets) — travels with the app
│   ├── functional.md  content.md  design-tokens.md  visual.md
│   ├── responsive.md  assumptions.md  constraints.md  assets.md
│   └── assets/        # generated placeholders + supplied assets
├── src/               # generated React app (App.jsx + src/components/*)
├── dist/              # built artifact → Netlify
└── gaps_report.md     # written when the visual budget is exhausted without a match
```

Placeholder images are generated at the correct size for each slot; **replace
them with real assets at the same filename** (or drop real images into
`input/references/`) to swap them in.

## Terminal states

| State                | Meaning                                              | Exit |
| -------------------- | ---------------------------------------------------- | ---- |
| `success`            | matched the reference and deployed                   | 0    |
| `deployed_with_gaps` | builds, visual budget exhausted, deployed best effort| 0    |
| `build_failed`       | could not produce a compiling build — no deploy      | 1    |
| `deploy_failed`      | built, but the Netlify deploy failed                 | 1    |

## Development

```bash
uv run pytest                       # run the test suite

# Debug: capture outgoing model requests (images summarized) for diagnosing
# provider HTTP errors.
PIPELINE_DEBUG_REQUESTS=1 uv run screenshot-to-react --name mylanding
# -> writes debug_requests.jsonl
```

The pipeline package is organized by stage:

```
pipeline/
├── core/       # shared: deps, config, results, logging, preflight, build tooling
├── analyst/    # stage, models, assets, writer
├── builder/    # stage, coding_agent, judges, graph, state
├── deployer/   # stage
├── cli.py  orchestrator.py  skills.py
```
