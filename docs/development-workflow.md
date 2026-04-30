# Cross-Repo Development Workflow

This document records the shared development workflow for the EasyAiMi service
repositories in this workspace.

## Active Development Repositories

Only develop in these repositories:

- `C:\Users\Public\nas_home\AI\GameEditor\EasyProxy`
- `C:\Users\Public\nas_home\AI\GameEditor\EasyEmail`
- `C:\Users\Public\nas_home\AI\GameEditor\EasyProtocol`
- `C:\Users\Public\nas_home\AI\GameEditor\EasyBrowser`
- `C:\Users\Public\nas_home\AI\GameEditor\EasyRegister`

Legacy repositories remain reference-only. They may be used for code
borrowing, migration comparison, and behavior lookup, but they are not write
targets for ongoing implementation work.

## Architecture Contract

- `EasyProxy`, `EasyEmail`, `EasyProtocol`, `EasyBrowser`, and
  `EasyRegister` are capability services on the private `EasyAiMi` Docker
  network.
- Services request capabilities from other services over the private container
  network instead of embedding downstream implementations locally.
- Inter-container traffic inside this private host-local network does not
  require extra service-to-service authentication.
- `EasyRegister` acts as an orchestrator and caller. It should request mailbox,
  proxy, protocol, and browser capabilities from the network.
- When a behavior fails, first identify which service actually owns the
  failing capability, then patch the corresponding new repository.

## Temporary Build And Test Assets

Use `C:\Users\Public\nas_home\AI\GameEditor\linshi` as the shared workspace
root for temporary local validation assets, including:

- temporary image build contexts
- temporary compose files
- temporary env files
- exported image tarballs
- throwaway logs and runtime artifacts

Do not spread short-lived local test assets across the main repositories when
they are not meant to be kept long term.

## Current Program Goal

The current migration milestone is to run the three historical DST flows on the
new stack:

- `main`
- `continue`
- `team`

Work should be prioritized toward getting these flows running end to end in the
new architecture before polishing secondary concerns.

## Daily Iteration Workflow

Use this loop for normal development:

1. Edit the owning new repository locally.
2. Build locally.
3. Test locally.
4. Run isolated local Docker validation against the new stack.

During rapid iteration, do not use GitHub Actions as the primary test loop.

When local validation requires containers, prefer isolated test containers,
ports, names, and output directories so existing long-running stacks are not
disturbed.

## Final Release Validation

After local build, test, and runtime validation are stable, run one final
release-grade verification:

1. Build through GitHub Actions.
2. Publish to GHCR.
3. Pull the GHCR images locally.
4. Run the target scenario locally from the pulled images.
5. Confirm the result is acceptable.

A migration or flow change is only considered fully validated after this final
GHCR-based verification passes.

## Legacy Reference Rule

Legacy repositories remain available for:

- logic comparison
- migration audits
- missing behavior lookup
- code borrowing during reconstruction

Legacy repositories are not the place for forward development in this program.
