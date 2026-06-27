## ADDED Requirements

### Requirement: Scaffold a Vite + React + Tailwind app
The builder SHALL generate the landing page as a Vite + React + Tailwind project in the output project directory, consuming the requirements set produced by the analyst. The builder SHALL operate as a coding agent with file tools (read/write/edit/list) scoped to the project directory, writing and editing files directly rather than returning a fixed set of file contents. It MAY decompose the UI into as many component files as good structure calls for; it SHALL always produce `src/App.jsx` (the default-export root) and `src/index.css` (starting with `@import "tailwindcss";`). On fix passes it SHALL edit files in place rather than regenerate from scratch.

#### Scenario: Build from requirements
- **WHEN** the builder runs with a populated `requirements/` directory
- **THEN** it produces a Vite + React + Tailwind app implementing the documented functional, visual, and responsive requirements

#### Scenario: Multi-file component structure
- **WHEN** the builder generates the app
- **THEN** it may split the UI into multiple component files (e.g. under `src/components/`) imported from `src/App.jsx`, written directly via its file tools

#### Scenario: Extracted assets imported
- **WHEN** the requirements include extracted asset files
- **THEN** the builder imports them into the app's asset pipeline (e.g. `public/` or `src/assets/`) so they are bundled

### Requirement: Render icons with an icon library
The scaffold SHALL include an icon library (lucide-react), and the builder SHALL render every icon visible in the reference (e.g. cart icon with badge, nav chevrons, carousel arrows, "+" add buttons, star ratings, "more info" arrows, footer social icons, hero overlay controls) using that library rather than substituting plain text. The analyst SHALL enumerate the visible icons so the builder can reproduce them. Hand-drawn inline SVG MAY be used only for a brand logo/wordmark the library does not provide.

#### Scenario: Reference icon reproduced
- **WHEN** the reference shows an icon (e.g. a cart icon)
- **THEN** the build renders the corresponding library icon, not a text substitute

#### Scenario: Icons enumerated by the analyst
- **WHEN** the analyst documents the page
- **THEN** the requirements list the visible icons for the builder to reproduce

### Requirement: Choose images by preference order
The builder SHALL be given an explicit list of the available asset files (with their served public paths) and SHALL fill each image slot using this preference order: (1) a user-supplied real asset mapped to the slot, (2) otherwise the generated placeholder file for the slot, (3) otherwise an external image URL as a last resort. The builder SHALL do its best to fill every slot and SHALL NOT treat placeholders as defects to remove.

#### Scenario: Supplied asset preferred
- **WHEN** a user-supplied asset is mapped to a section's image slot
- **THEN** the builder references that supplied asset by its public path rather than a placeholder or external image

#### Scenario: Placeholder used when no supplied asset
- **WHEN** a slot has no supplied asset
- **THEN** the builder references the generated placeholder for that slot by its public path

#### Scenario: External image only as last resort
- **WHEN** no supplied asset or placeholder fits an image slot
- **THEN** the builder may use an external image URL for that slot

### Requirement: Enforce a build-success contract
The build SHALL succeed before any verification proceeds. A compile/build failure SHALL trigger a fix routed back to the build step, governed by a separate global build-fix budget. If the build-fix budget is exhausted without a successful build, the pipeline SHALL hard-stop and SHALL NOT deploy.

#### Scenario: Compile error fixed within budget
- **WHEN** the generated app fails to build but the build-fix budget is not exhausted
- **THEN** the builder fixes the compile error and rebuilds, without consuming the visual fix budget

#### Scenario: Build-fix budget exhausted
- **WHEN** the app still fails to build after the build-fix budget is exhausted
- **THEN** the pipeline hard-stops, reports the failure, and does not deploy

### Requirement: Run an advisory quality gate
The builder SHALL run lint and accessibility (axe) checks as an advisory step that records findings but never blocks or loops. Findings MAY be folded into the gaps report or judge discrepancies.

#### Scenario: Lint/a11y findings recorded
- **WHEN** the advisory quality gate finds lint or a11y issues
- **THEN** the findings are recorded AND the pipeline continues to preview without looping on them

### Requirement: Capture the built page at the inferred viewport
After a successful build, the builder SHALL start a preview server, wait until the page is rendered, and capture a Playwright screenshot at the viewport width inferred by the analyst.

#### Scenario: Screenshot at reference width
- **WHEN** the preview server is ready
- **THEN** Playwright captures the page at the inferred viewport width

### Requirement: Judge visual fidelity with a structured verdict
A vision LLM judge SHALL compare the captured screenshot to the reference and return a structured verdict containing a match flag, a similarity estimate, and a list of discrepancies (region, issue, severity). The judge SHALL be history-aware across attempts, carrying prior verdicts while trimming image history. The judge SHALL only evaluate the shown reference viewport and SHALL NOT fail the build for responsive or interaction behavior not visible in the reference. The judge SHALL treat neutral placeholder images as expected and SHALL NOT raise a discrepancy or lower similarity merely because an image is a placeholder rather than the real photo; it SHALL judge placeholders on size and position only. The loop SHALL treat a similarity estimate at or above the configured threshold as a match, regardless of the judge's boolean match flag, so that expected placeholder stand-ins do not prevent success once layout fidelity is high.

#### Scenario: Match reached on similarity threshold
- **WHEN** the judge's similarity estimate is at or above the configured threshold
- **THEN** the verify loop treats it as a match and exits successfully, even if the judge's boolean flag is false (e.g. due to placeholder images)

#### Scenario: Discrepancies reported
- **WHEN** the build does not match
- **THEN** the verdict lists discrepancies with region, issue, and severity for the builder to address

#### Scenario: Placeholder not flagged as a defect
- **WHEN** the build shows a correctly-sized, correctly-placed placeholder where the reference has a real photo
- **THEN** the judge does not raise it as a discrepancy and does not lower similarity for it

#### Scenario: Placeholder complaints not sent to the builder
- **WHEN** a verdict still contains a discrepancy that only says a placeholder stands in for a real photo
- **THEN** the builder is not given that complaint to fix and is instructed to keep placeholders as-is

#### Scenario: Out-of-scope behavior ignored
- **WHEN** responsive behavior at a non-reference width differs from an assumption
- **THEN** the fidelity judge does not flag it as a discrepancy

### Requirement: Check responsive sanity at a mobile viewport
Because no reference screenshot exists for non-reference viewports, the loop SHALL evaluate responsiveness by capturing the built page at a mobile width (default 375px) and asking a vision judge whether the layout is a sane, non-broken responsive layout consistent with the documented responsive assumptions. The responsive verdict SHALL distinguish objective breakage (a hard `broken` signal: horizontal overflow, content/elements wider than the viewport, overlapping or clipped content) from non-blocking structured suggestions (region + actionable improvement). Suggestions SHALL be limited to high-impact responsiveness or user-experience improvements (capped to a small number, e.g. 3); low-value cosmetic nitpicks SHALL be omitted, and an already-usable layout SHALL yield zero suggestions, so the builder is not confused by trivia. Objective breakage SHALL block a match and SHALL be added to the discrepancies the builder must fix. Suggestions SHALL NOT block a match; they SHALL be recorded and offered to the builder as optional improvements on a subsequent fix pass.

#### Scenario: Mobile layout is broken
- **WHEN** the mobile capture shows objective breakage (e.g. horizontal overflow or an element wider than the viewport)
- **THEN** the responsive verdict marks it broken, it blocks a match, and the breakage is added to the builder's fix discrepancies

#### Scenario: Mobile layout is sane
- **WHEN** the mobile capture is a sane responsive layout with no objective breakage
- **THEN** responsiveness does not block a match

#### Scenario: Responsive suggestions offered
- **WHEN** the responsive judge returns non-blocking improvement suggestions
- **THEN** the suggestions are recorded and offered to the builder as optional improvements without blocking the match

#### Scenario: Only high-impact suggestions surface
- **WHEN** the mobile layout is already usable with only minor cosmetic imperfections
- **THEN** the judge returns no (or at most a few high-impact) suggestions, so the builder is not confused by low-value nitpicks

#### Scenario: Responsive assumptions honored
- **WHEN** the requirements document responsive assumptions (e.g. nav collapses, columns stack)
- **THEN** the responsive judge evaluates the mobile capture against those assumptions

### Requirement: Bound the visual fix loop
The verify loop SHALL allow an initial build plus up to 3 visual fix attempts. On each fix the builder SHALL receive the reference, the discrepancies, and its own last screenshot, and SHALL be instructed to modify only flagged regions. When the visual budget is exhausted without a match, the loop SHALL emit a gaps report and allow deployment of the best attempt.

#### Scenario: Fix within budget
- **WHEN** the judge reports discrepancies and fewer than 3 visual attempts have been used
- **THEN** the builder fixes the flagged regions and the loop re-runs build, quality, preview, and judge

#### Scenario: Visual budget exhausted
- **WHEN** 3 visual fix attempts have been used without a match
- **THEN** the loop emits a gaps report describing remaining discrepancies and exits to allow deploying the best attempt
