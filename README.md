# screenshot-to-react

An agentic pipeline that takes an **instructions file** plus a **reference
landing-page screenshot** and produces a **deployed, responsive React landing
page**. It runs three stages in a fixed, deterministic order:

1. **Analyst** — vision+text analysis of the screenshot and instructions into an
   auditable requirements set (with an assumption ledger).
2. **Builder/Verifier** — a `pydantic_graph` state machine that scaffolds a
   Vite + React + Tailwind app, enforces a build-success contract, and iterates
   on visual fidelity using a vision judge (initial build + up to 3 fixes).
3. **Deployer** — builds a fresh `dist/` and deploys to Netlify.

## Requirements

### Python (managed with uv)

This is a Python project managed entirely with [uv](https://docs.astral.sh/uv/).
Use `uv add` for dependencies and `uv run` to execute commands — do not use
pip/poetry/venv directly.

```bash
uv sync                       # install dependencies
uv run playwright install chromium   # one-time browser install
```

### System toolchain (for the generated app)

The generated landing page is a Node/Vite project, so the following must be
available. The pipeline performs a runtime **toolchain preflight** that
auto-installs npm-based tools when missing and fails loudly for system-level
tools:

| Tool             | Minimum | Provisioning                                  |
| ---------------- | ------- | --------------------------------------------- |
| Node.js          | 18.14+  | **system-level** — fail loud if missing       |
| npm / npx        | bundled | with Node.js                                  |
| Playwright       | —       | `uv run playwright install chromium`          |
| Vite/React/Tailwind | —    | scaffolded per-run via `npx`                  |
| Netlify CLI      | —       | auto-installed via `npx`/`npm` when missing   |

## Environment variables

| Variable             | Required for | Purpose                                        |
| -------------------- | ------------ | ---------------------------------------------- |
| `NETLIFY_AUTH_TOKEN` | deploy       | Netlify authentication (CI-style, no browser). |
| LLM provider key     | analyst+judge| e.g. `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`.   |

`NETLIFY_AUTH_TOKEN` is **required** for the deploy stage. The deployer fails
loudly with an actionable message when it is missing.

## Usage

```bash
uv run screenshot-to-react --name mylanding
```

Inputs are read from the `input/` convention:

```
input/
├── instructions.md
└── references/
    └── <screenshot>.png
```

Output is written to a sibling project directory named by `--name`:

```
<name>/
├── requirements/      # analyst output (+ extracted assets) — travels with the app
├── src/ index.html …  # generated React app
└── dist/              # built artifact → Netlify
```
