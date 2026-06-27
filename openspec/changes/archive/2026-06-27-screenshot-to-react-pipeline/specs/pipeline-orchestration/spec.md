## ADDED Requirements

### Requirement: Deterministic three-stage sequence
The pipeline SHALL run the analyst, then the builder/verifier, then the deployer in a fixed deterministic order. No LLM SHALL decide the order of stages.

#### Scenario: Stages run in order
- **WHEN** the pipeline is invoked with valid inputs
- **THEN** it runs analyst, then builder/verifier, then deployer, in that order

### Requirement: Accept inputs by convention with parameterized output name
The pipeline SHALL read its inputs from an `input/` convention (an instructions file and a `references/` directory containing the screenshot) and SHALL write the output to a sibling project directory named by a `--name` parameter.

#### Scenario: Named output project
- **WHEN** the pipeline is invoked with `--name mylanding`
- **THEN** output is written to a sibling `mylanding/` directory while inputs are read from `input/`

#### Scenario: Multiple pages coexist
- **WHEN** the pipeline is run again with a different `--name`
- **THEN** a separate sibling output directory is created without overwriting the first

### Requirement: Share pipeline dependencies across stages
The pipeline SHALL thread shared dependencies (input paths, reference screenshot, output workdir, requirements directory, inferred viewport width, and fix budgets) through all stages.

#### Scenario: Shared deps available downstream
- **WHEN** the analyst records the inferred viewport width
- **THEN** the builder's capture step uses that same width via the shared dependencies

### Requirement: Distinct terminal states
The pipeline SHALL distinguish these terminal states: a hard-stop build-failure state (build could not be produced: no deploy), a deploy-failure state (the app built but deployment itself failed, e.g. bad credentials), a deploy-with-gaps state (visual budget exhausted: deploy best attempt), and a success state (match reached: deploy). Build-failure and deploy-failure SHALL be reported as failures (non-zero exit), while success and deploy-with-gaps are successful outcomes.

#### Scenario: Build failure terminal state
- **WHEN** the app cannot be built within the build-fix budget
- **THEN** the pipeline ends in a hard-stop state with no deployment and a non-zero exit

#### Scenario: Deploy failure terminal state
- **WHEN** the app builds but the deployment step fails (e.g. invalid Netlify credentials)
- **THEN** the pipeline ends in a deploy-failure state reporting the deploy error with a non-zero exit

#### Scenario: Deploy-with-gaps terminal state
- **WHEN** the visual budget is exhausted but the app builds and deploys
- **THEN** the pipeline deploys the best attempt and reports gaps

#### Scenario: Success terminal state
- **WHEN** the judge reports a match within budget and deployment succeeds
- **THEN** the pipeline deploys the matched build

### Requirement: Verify and provision the toolchain before stages run
The pipeline SHALL perform a toolchain preflight that verifies the CLI tools and runtimes each stage requires (e.g. Node.js, the Vite/React/Tailwind toolchain, Playwright browsers, the Netlify CLI). For tools that are safe to install programmatically (npm-based tools such as `netlify-cli` and Playwright browsers), the preflight SHALL install them automatically when missing. For tools that require privileged or system-level installation (e.g. Node.js itself), the preflight SHALL fail loudly with a clear, actionable message rather than attempting installation. The preflight MAY consult the installed skills for the correct install commands.

#### Scenario: Safe tool missing
- **WHEN** an npm-based tool such as `netlify-cli` or the Playwright browsers are not present
- **THEN** the preflight installs them automatically and continues

#### Scenario: System-level tool missing
- **WHEN** a required runtime such as Node.js is missing or below the minimum version
- **THEN** the preflight fails with a clear message stating what is required and how to install it, and does not attempt a privileged install

#### Scenario: Toolchain already satisfied
- **WHEN** all required tools are present at acceptable versions
- **THEN** the preflight passes without installing anything and the stages proceed

### Requirement: Mount runtime skills for the builder
The builder agent SHALL mount the installed skills directory via a skills capability so React, Tailwind, accessibility, Playwright, and Netlify guidance is available at runtime through progressive disclosure. The pipeline SHALL record which skill tools the model invokes and report whether any skills were loaded during the run.

#### Scenario: Builder loads a skill on demand
- **WHEN** the builder is styling the page
- **THEN** it can load the relevant best-practice skill on demand rather than having all guidance preloaded

#### Scenario: Skill usage reported
- **WHEN** the builder run completes
- **THEN** the pipeline reports the skill tool calls made and the distinct skills loaded (or that none were used)

### Requirement: Configure models per stage
The pipeline SHALL allow selecting the LLM model per stage (analyst, builder, fix-build, judge) via configuration, with a global default and a documented fallback chain. Configuration SHALL be readable from environment variables so it can live in a `.env` file.

#### Scenario: Global default applies to all stages
- **WHEN** only a global model is configured
- **THEN** every stage uses that model

#### Scenario: Per-stage override
- **WHEN** a per-stage model is configured for one stage
- **THEN** that stage uses the override while other stages keep the global default

### Requirement: Configure inputs from environment
The pipeline SHALL resolve its inputs (output name, top directory, instructions file, references directory, skills directory) from environment variables as defaults, with command-line flags overriding them when provided.

#### Scenario: Run from environment configuration
- **WHEN** the path configuration is provided via environment variables and no overriding flags are passed
- **THEN** the pipeline runs using the environment-provided paths

#### Scenario: Flag overrides environment
- **WHEN** a command-line flag is provided for a value also set in the environment
- **THEN** the flag value takes precedence

### Requirement: Report run progress
The pipeline SHALL emit human-readable progress logs covering each stage and each iteration of the build/verify loop (generation, build attempts, capture, judge verdicts with discrepancies, and fixes) so a run is observable.

#### Scenario: Progress is observable
- **WHEN** the pipeline runs
- **THEN** it logs stage starts/completions and per-iteration build and judge activity
