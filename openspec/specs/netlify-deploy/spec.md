# netlify-deploy Specification

## Purpose
TBD: created by syncing the screenshot-to-react-pipeline change. Update Purpose after review.

## Requirements

### Requirement: Build a fresh artifact before deploy
The deployer SHALL build a fresh production artifact (`dist/`) immediately before deploying, so the deployed output reflects the final state of the app.

#### Scenario: Fresh build before deploy
- **WHEN** the deployer runs
- **THEN** it produces a fresh `dist/` and deploys that artifact

### Requirement: Require Netlify authentication
The deployer SHALL require a `NETLIFY_AUTH_TOKEN` and SHALL fail loudly with a clear message when it is missing.

#### Scenario: Missing token
- **WHEN** `NETLIFY_AUTH_TOKEN` is not set
- **THEN** the deployer stops with an explicit error and does not attempt deployment

### Requirement: Deploy idempotently
The deployer SHALL reuse an existing Netlify site id when present so repeated runs update the same site rather than creating new ones; when no site id exists it MAY create a new site.

#### Scenario: Re-run reuses site
- **WHEN** a site id already exists for the output project
- **THEN** the deployer deploys to the same site

#### Scenario: First run creates site
- **WHEN** no site id exists
- **THEN** the deployer creates a new site and records its id for future runs

### Requirement: Deploy best attempt with gaps report
When the visual budget was exhausted without a perfect match, the deployer SHALL deploy the best attempt and surface the gaps report describing remaining discrepancies. It SHALL only refuse to deploy when the app does not build.

#### Scenario: Imperfect but building
- **WHEN** the visual budget was exhausted but the app builds
- **THEN** the deployer deploys the best attempt and reports the remaining gaps

#### Scenario: Non-building app
- **WHEN** the app does not build
- **THEN** the deployer does not deploy
