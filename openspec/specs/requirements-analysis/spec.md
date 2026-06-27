# requirements-analysis Specification

## Purpose
TBD: created by syncing the screenshot-to-react-pipeline change. Update Purpose after review.

## Requirements

### Requirement: Reconcile instructions and screenshot
The analyst agent SHALL read the instructions file (text) and the reference screenshot (vision) and produce a single reconciled requirements set. The reference screenshot SHALL be identified by a reserved base name (e.g. `screenshot.*` or `landingpage.*`) so that other image files in the references directory are not mistaken for the screenshot. When the instructions and the screenshot conflict, the instructions SHALL take precedence, and the conflict SHALL be recorded in the requirements.

#### Scenario: Conflicting CTA text
- **WHEN** the instructions specify CTA text "Start free trial" but the screenshot shows "Get started"
- **THEN** the requirements record "Start free trial" as the CTA text AND note the conflict and that instructions overrode the screenshot

#### Scenario: Screenshot-only detail
- **WHEN** the screenshot shows a section the instructions do not mention
- **THEN** the requirements include that section derived from the screenshot

### Requirement: Infer reference viewport width
The analyst SHALL infer the viewport kind represented by the reference screenshot (e.g. desktop/tablet/mobile) and record it. The capture width used downstream SHALL be the screenshot's actual pixel width; when the model's inferred width diverges from the actual image width, the system SHALL override it with the actual width and record that the override occurred. This prevents a tall full-page capture from being misread as a narrow viewport.

#### Scenario: Desktop screenshot
- **WHEN** the screenshot is a wide desktop capture
- **THEN** the requirements record an inferred desktop viewport whose capture width equals the screenshot's actual pixel width used for later Playwright capture

#### Scenario: Inferred width diverges from the image
- **WHEN** the model infers a width that differs from the screenshot's actual pixel width
- **THEN** the system overrides the capture width with the actual image width and records that the override happened

### Requirement: Maintain an assumption ledger
The analyst SHALL stamp every inference not directly evidenced by the screenshot as `ASSUMED` in the requirements, including responsive breakpoints, mobile navigation, hover/focus states, and below-the-fold content.

#### Scenario: Responsive breakpoint not shown
- **WHEN** the screenshot is a single desktop viewport with no mobile evidence
- **THEN** the requirements record the mobile breakpoint and nav behavior tagged `ASSUMED`

#### Scenario: Directly evidenced detail
- **WHEN** a layout detail is clearly visible in the screenshot
- **THEN** that detail is recorded as evidenced (not `ASSUMED`)

### Requirement: Record fidelity-vs-accessibility rulings
The analyst SHALL decide, per case, whether visual fidelity or accessibility correctness wins when they conflict, and record the ruling so the builder and judge act consistently.

#### Scenario: Low-contrast text in reference
- **WHEN** the screenshot shows text that fails WCAG contrast
- **THEN** the requirements record a ruling (e.g. raise contrast despite divergence) for the builder and judge to honor

### Requirement: Catalog assets
The analyst SHALL catalog assets implied by the screenshot (logos, images, icons, fonts) in an asset manifest, choosing per asset to recreate (CSS/SVG) or placeholder. The analyst SHALL NOT crop regions out of the screenshot: pixel extraction from a tall full-page capture is unreliable, so assets are reproduced as code (recreate) or stood in as placeholders, and the builder may also use external images. Each manifest entry SHALL describe what the asset depicts and where it belongs so the builder can reproduce or source it.

#### Scenario: Logo present in screenshot
- **WHEN** a logo appears in the reference
- **THEN** the manifest records the logo as `recreate` (inline SVG/CSS) with a description of its appearance and placement

#### Scenario: Photographic image needed
- **WHEN** a section needs a photo that cannot be reproduced in code
- **THEN** the manifest records it as a `placeholder` with a description and ratio so the builder can stand it in or source an external image

#### Scenario: Asset cannot be cleanly sourced
- **WHEN** an asset (e.g. brand font) cannot be recreated
- **THEN** the manifest marks it as a placeholder and flags it as a known gap

### Requirement: Use supplied reference assets
The analyst SHALL treat image files in the references directory other than the reference screenshot as user-supplied assets available to the build. The analyst SHALL be given the list of these files (and their images) and SHALL map each appropriate one to a slot, recording it in the manifest with a strategy that uses the supplied file rather than generating a placeholder. Supplied asset files SHALL be copied into the output project's asset directory so the build can reference them by name. The analyst MAY be given read-only file tools scoped to the references directory to discover additional reference material itself; it SHALL NOT write files (its output remains the structured requirements).

#### Scenario: Analyst discovers reference material
- **WHEN** the references directory contains extra files beyond the main screenshot
- **THEN** the analyst may use its read-only file tools to discover and factor them in, while still producing structured requirements (no files written by the analyst)

#### Scenario: Supplied asset mapped to a slot
- **WHEN** the references directory contains a real image (e.g. a hero photo) alongside the screenshot
- **THEN** the analyst maps it to the matching slot and the manifest records it as a supplied asset, and no placeholder is generated for that slot

#### Scenario: Supplied asset unused
- **WHEN** a supplied image does not correspond to any slot the analyst identifies
- **THEN** it is still copied into the output assets so the builder may use it, and the manifest notes it as available

### Requirement: Extract structured design tokens
The analyst SHALL extract structured design tokens from the screenshot — at minimum a named color palette (token name + hex), a spacing scale, a type scale (sizes and weights), and border radii — recorded in a dedicated `design-tokens.md`. Tokens SHALL be structured so the builder can map them to Tailwind's `@theme` rather than re-deriving values from prose. Each token MAY carry provenance (evidenced vs. assumed).

#### Scenario: Colors captured as named tokens
- **WHEN** the screenshot uses a distinct brand color
- **THEN** `design-tokens.md` records it as a named token with its hex value (e.g. `primary: #1a73e8`)

#### Scenario: Scales captured for fidelity
- **WHEN** the analyst infers spacing, type sizes, or radii from the design
- **THEN** `design-tokens.md` records them as a structured scale the builder maps into Tailwind `@theme`

### Requirement: Separate page content
The analyst SHALL record all page copy, calls-to-action, and link targets in a dedicated `content.md`, separate from layout and behavior, so content is auditable independently of structure.

#### Scenario: Copy recorded in content.md
- **WHEN** the page has headlines, body copy, CTAs, and links
- **THEN** `content.md` lists them grouped by section, distinct from the layout/behavior notes

### Requirement: Write requirements into the output project
The analyst SHALL create the output project directory and write the requirements set inside it (e.g. `<name>/requirements/`) so the requirements and extracted assets travel with the product. The set SHALL include at least `functional.md`, `content.md`, `visual.md`, `design-tokens.md`, `non-functional.md`, `responsive.md`, `assumptions.md`, `constraints.md`, and the `assets.md` manifest (plus the `assets/` directory).

#### Scenario: Requirements created before build
- **WHEN** the analyst runs
- **THEN** the output project directory exists with a populated `requirements/` directory and `assets/` before the builder runs

#### Scenario: Token and content files present
- **WHEN** the analyst completes
- **THEN** `design-tokens.md` and `content.md` exist alongside the other requirement files
