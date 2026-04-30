# EasyBrowser Request / Response Contract

This file defines the current **interface skeleton**, not a final API contract.

The goal is to normalize how callers talk to `EasyBrowser` regardless of
whether the selected backend is:

- `chrome`
- `camoufox`
- `browserbase`

## Primary Public Flow

### 1. Submit execution request

Logical operation:

- caller submits one execution request
- request chooses either:
  - `strategy` mode
  - `direct` mode

Expected output:

- accepted / rejected decision
- `task_id`
- normalized routing summary
- optional `runtime_id` when allocation is immediate

### 2. Poll task status

Logical operation:

- caller queries the current task state

Expected output:

- task state
- provider / runtime routing info
- normalized error info when failed
- normalized result info when succeeded

## Request Families

### Public request family

Caller-facing requests should eventually normalize around these concepts:

- request identity
- route mode
- requested operation
- operation payload
- timeout / retry hints
- isolation preference
- provider restrictions or direct target

### Admin request family

Operator-facing requests should eventually normalize around:

- provider inspection
- runtime inspection
- cooldown inspection
- forced disable / enable
- pool limits or strategy toggles

### Internal request family

Internal coordination requests should eventually normalize around:

- runtime registration
- runtime health updates
- child-process supervisor events
- task-to-runtime completion signals

## Response Normalization

Every response family should eventually provide a normalized envelope:

- `success`
- `code`
- `message`
- `data`
- `error`
- `trace`

Where:

- `data` carries the successful payload
- `error` carries normalized failure details
- `trace` carries request / task / provider / runtime identifiers

## Important Boundary

The contract should normalize output across:

- local providers
- remote providers
- fresh runtime allocations
- reused runtime allocations

Callers should not need provider-specific response parsing for ordinary use.
