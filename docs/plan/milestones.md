# Milestones

## M1: Public Target Skeleton Ready

Criteria:

- `EasyBrowser` target repo exists
- root structure is established
- planning and progress docs are present
- copy-only rules are documented in the target repo

## M2: `service/base` Imported and Sanitized

Criteria:

- current EasyBrowser service source is copied into `service/base`
- generated binaries are removed from the target import
- basic build/test path works from the new monorepo layout

## M3: Runtime and Upstream Areas Imported

Criteria:

- `runtimes/chrome` is imported
- `upstreams/camoufox` exists with correct boundary semantics
- `upstreams/geekez-browser` is imported without local build/install outputs
- service/base path bindings are updated to the new layout

## M4: GitHub Actions and GHCR Publish Live

Criteria:

- validation workflow exists and is runnable
- GHCR publish workflow exists and is documented
- root scripts support config materialization and image build/publish flows

## M5: Public Publication Readiness

Criteria:

- migration completeness audit is finished
- public repo scrub for secrets/artifacts is finished
- contributor docs and release checklist are complete
- the repo is ready for first GitHub publication
