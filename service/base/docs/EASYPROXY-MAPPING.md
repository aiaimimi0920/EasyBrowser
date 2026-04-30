# EasyProxy-to-EasyBrowser Framework Mapping

This file records the current interpretation of the local `EasyProxiesV2`
patterns and how they map into `EasyBrowser`.

## What was taken from EasyProxiesV2

After reviewing the local EasyProxiesV2 code and structure, the important
framework-level ideas are:

- one unified management/API surface instead of backend-specific APIs
- strategy-style runtime selection
- explicit/direct targeting when needed
- failure counting and blacklist/cooldown style protection
- runtime snapshots and status views
- operator controls for health, reload, and maintenance

## How those ideas map into EasyBrowser

### strategy mode

Mapped into:

- provider ranking in the parent service
- candidate filtering by:
  - enabled state
  - cooldown state
  - ready runtime count
  - recent failures

### specified/direct mode

Mapped into:

- direct provider selection through request mode
- acceptance of both:
  - `direct`
  - `specified`

### error cooling

Mapped into:

- provider-level cooldown state
- runtime-level cooldown state
- cooldown reset endpoint

### error attribution

Mapped into:

- normalized error category on task/runtime/provider failures
- per-provider error category counters
- per-runtime error category counters

### unified API surface

Mapped into:

- public task API
- admin provider/runtime/stats API
- internal runtime registration / heartbeat / completion API
