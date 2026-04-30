# Task Breakdown

## Phase 1: Repository Bootstrap

### Lane A

#### P1-1

- Priority: P0
- Effort: S
- Description: create the public `EasyBrowser` repo skeleton with root layout,
  readme, ignore policy, config example, docs, and progress tracking
- Dependencies: none
- Acceptance criteria:
  - target repo exists
  - root layout matches the planned monorepo structure
  - no source-workspace files are modified

#### P1-2

- Priority: P0
- Effort: M
- Description: document the old-to-new mapping and copy-only migration rules in
  root docs and progress files
- Dependencies: P1-1
- Acceptance criteria:
  - contributors can understand the migration contract from the new repo alone
  - source-to-target mapping is explicit

### Lane B

#### P1-3

- Priority: P1
- Effort: M
- Description: define the target root config sections and initial root operator
  script conventions using the `EasyEmail` model
- Dependencies: P1-1
- Acceptance criteria:
  - root `config.example.yaml` exists
  - planned config ownership is documented

Merge risk:

- Low

## Phase 2: Import `service/base`

### Lane A

#### P2-1

- Priority: P0
- Effort: L
- Description: copy `BrowserService\repos\EasyBrowser` into `service/base`
  without altering the source repo
- Dependencies: P1-1, P1-2
- Acceptance criteria:
  - target `service/base` contains the current EasyBrowser source tree
  - the source repo remains untouched

#### P2-2

- Priority: P0
- Effort: M
- Description: remove target-side generated binaries, logs, and local-only
  workspace artifacts from the imported `service/base`
- Dependencies: P2-1
- Acceptance criteria:
  - compiled `.exe` files are not tracked in the public repo
  - only intended public source remains

### Lane B

#### P2-3

- Priority: P0
- Effort: M
- Description: rewrite internal path assumptions so the control plane resolves
  runtime and deploy assets inside the new monorepo layout
- Dependencies: P2-1
- Acceptance criteria:
  - service-base no longer depends on old BrowserService absolute/relative paths

#### P2-4

- Priority: P1
- Effort: M
- Description: move repository-local docs and smoke scripts into the new target
  structure while preserving behavior
- Dependencies: P2-1
- Acceptance criteria:
  - `service/base/docs` and root/deploy scripts are coherent in the new layout

Merge risk:

- Medium

## Phase 3: Import Runtimes and Upstreams

### Lane A

#### P3-1

- Priority: P0
- Effort: M
- Description: copy `repos/chrome` into `runtimes/chrome`
- Dependencies: P2-3
- Acceptance criteria:
  - target runtime code is present
  - source workspace is unchanged

#### P3-2

- Priority: P0
- Effort: M
- Description: adapt service-base runtime spawn/config code to the new
  `runtimes/chrome` path
- Dependencies: P3-1
- Acceptance criteria:
  - service-base references the new runtime path layout correctly

### Lane B

#### P3-3

- Priority: P1
- Effort: S
- Description: copy the Camoufox fork slot into `upstreams/camoufox`
- Dependencies: P1-1
- Acceptance criteria:
  - upstream directory exists in the public repo with correct intent docs

#### P3-4

- Priority: P1
- Effort: XL
- Description: sanitize and copy `repos/GeekezBrowser` into
  `upstreams/geekez-browser`
- Dependencies: P1-1, P1-2
- Acceptance criteria:
  - target excludes `node_modules/`, `out/`, logs, and local-only outputs
  - public source and lockfiles remain intact

Merge risk:

- Medium for P3-1/P3-2
- High for P3-4 because of subtree size and sanitization scope

## Phase 4: CI/CD and GHCR

### Lane A

#### P4-1

- Priority: P0
- Effort: M
- Description: add `validate.yml` to run root-level validation for `service/base`
  and lightweight runtime checks
- Dependencies: P2-2, P2-3, P3-1, P3-2
- Acceptance criteria:
  - GitHub Actions can run repository validation on pull requests

#### P4-2

- Priority: P0
- Effort: L
- Description: add `publish-service-base-ghcr.yml` plus supporting scripts for
  GHCR image publishing
- Dependencies: P4-1
- Acceptance criteria:
  - tagged or manual workflow can build and publish the service image

### Lane B

#### P4-3

- Priority: P1
- Effort: M
- Description: add root scripts for config materialization, image build, and
  smoke validation modeled after EasyEmail
- Dependencies: P1-3, P2-4
- Acceptance criteria:
  - root scripts exist for common operator flows

#### P4-4

- Priority: P1
- Effort: M
- Description: document GitHub Actions secrets and release workflow in root docs
- Dependencies: P4-2
- Acceptance criteria:
  - a new operator can configure CI/CD from repo docs alone

Merge risk:

- Low

## Phase 5: Public Hardening and Verification

### Lane A

#### P5-1

- Priority: P0
- Effort: M
- Description: audit migrated content against the source workspace and produce
  an omission list, not just a confidence statement
- Dependencies: P2-4, P3-4, P4-4
- Acceptance criteria:
  - every planned mapping is checked
  - any missing content is enumerated explicitly

#### P5-2

- Priority: P0
- Effort: M
- Description: review the public repo for secrets, local-only state, and
  generated artifacts before publication
- Dependencies: P2-2, P3-4, P4-4
- Acceptance criteria:
  - public repo contains no obvious private material

### Lane B

#### P5-3

- Priority: P1
- Effort: M
- Description: polish contributor-facing README, quickstart, and repository map
- Dependencies: P4-4
- Acceptance criteria:
  - the repo is understandable without access to the old workspace

#### P5-4

- Priority: P1
- Effort: M
- Description: define release tagging and first-publish checklist
- Dependencies: P4-2, P4-4
- Acceptance criteria:
  - release workflow is documented and reproducible

Merge risk:

- Low
