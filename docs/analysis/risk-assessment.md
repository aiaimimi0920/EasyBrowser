# Risk Assessment

## P0 Risks

### 1. Copy-only boundary violation

Risk:

- migration work accidentally edits the source workspace instead of the new
  public target repo

Impact:

- breaks the user's hard constraint
- risks damaging the internal working environment

Mitigation:

- treat `BrowserService` as read-only source material
- create all new docs, scripts, CI, and path rewrites only under
  `C:\Users\Public\nas_home\AI\GameEditor\EasyBrowser`
- when importing, prefer file-by-file or directory-copy operations into the new
  repo rather than in-place moves

### 2. Public repo contamination by local artifacts

Risk:

- binaries, caches, `node_modules/`, logs, or runtime outputs are copied into
  the new public repo

Evidence:

- `repos/EasyBrowser` includes many `.exe` outputs
- `repos/GeekezBrowser` currently includes `node_modules/` and `out/`

Impact:

- huge noisy diffs
- broken contributor experience
- accidental release of local-only build products

Mitigation:

- import only source-tracked and intentionally public files
- define target-root `.gitignore` before code copy
- audit each imported subtree against source ignore rules

### 3. Secret and private-material leakage

Risk:

- the public monorepo accidentally pulls in `AIRead`-style secret references or
  local deployment state

Impact:

- exposure of private tokens or internal operator data

Mitigation:

- keep `AIRead` entirely out of scope
- centralize public operator config to `config.example.yaml` plus local ignored
  `config.yaml`
- rewrite any deploy docs or scripts that still assume private local files

## P1 Risks

### 4. Architecture drift between docs and implementation

Risk:

- docs position EasyBrowser mainly as a browser-resource allocator, but the
  implementation already contains medium-step register/repair browser flows

Impact:

- unclear public scope
- harder contributor mental model
- future API break risk

Mitigation:

- explicitly decide during migration whether `service/base` publicly owns only
  primitive browser control plus leasing, or also medium-step flow orchestration
- document the chosen boundary in root architecture docs before deeper code move

### 5. Runtime implementation inconsistency

Risk:

- current runtime direction is mixed:
  - docs describe Chrome runtime as Node/TypeScript-friendly
  - actual Chrome migration line is Python-heavy
  - EasyBrowser still carries a Node-based Chrome adapter file

Impact:

- confusing build/test matrix
- unclear ownership of runtime code

Mitigation:

- keep migration faithful first
- postpone runtime-language consolidation until after source import
- document the exact live launch path that the public repo should preserve

### 6. CI matrix complexity

Risk:

- the repo spans Go, Python, Node/Electron, and possibly browser assets

Impact:

- GitHub Actions can become fragile or too expensive if everything is validated
  in one workflow from day one

Mitigation:

- phase CI:
  - first validate `service/base`
  - then add lightweight checks for `runtimes/chrome`
  - keep heavy upstream build jobs isolated and optional until stable

### 7. Oversized upstream import

Risk:

- `GeekezBrowser` may dominate repo size and CI time even after sanitization

Impact:

- poor clone experience
- slow CI
- noisy contributor workflow

Mitigation:

- import only source and lockfiles, exclude local install/build outputs
- re-check whether large binary resources inside the upstream fork are truly
  required for public source distribution

## P2 Risks

### 8. Root config under-specification

Risk:

- adopting one root config too late can force repeated path rewrites

Impact:

- scripts and workflows drift apart

Mitigation:

- define root config sections early:
  - `serviceBase.runtime`
  - `chromeRuntime`
  - `publishing.ghcr`
  - future provider/runtime sections as needed

### 9. Workflow naming drift

Risk:

- publish/deploy scripts and workflow names end up inconsistent with the final
  repo layout

Impact:

- poor discoverability

Mitigation:

- align early on `EasyEmail`-style naming:
  - `validate.yml`
  - `publish-service-base-ghcr.yml`
  - root `scripts/` entrypoints with service-base terminology

## Recommended Sequencing Guardrails

- import planning and skeleton first
- import `service/base` before other code because it defines the repo contract
- import `runtimes/chrome` next because it is self-owned and relatively compact
- sanitize `upstreams/geekez-browser` before copying
- delay heavy CI and release automation until paths stabilize
