# EasyBrowser Cooling and Stats Flow

This file records the current cooling / statistics dataflow skeleton.

## Core Principle

Cooling and stats should be updated around normalized events, not around
provider-specific raw behavior alone.

## Main Event Types

Typical events that should feed stats later:

- request accepted
- route selected
- runtime allocated
- runtime startup failed
- task execution succeeded
- task execution failed
- task timed out
- child process exited unexpectedly
- runtime recovered successfully
- cooldown entered
- cooldown cleared

## Stats Layers

### Provider-level stats

Used for:

- strategy routing input
- operator visibility
- provider-level cooldown triggers

### Runtime-level stats

Used for:

- per-process health analysis
- runtime quarantine decisions
- restart policy evaluation

## Cooling Triggers

Cooling may be triggered by:

- repeated startup failures
- repeated execution failures
- repeated transport failures
- repeated abnormal child-process exits

## Cooling Scope

Cooling may apply to:

- provider-level route suppression
- runtime-instance-level suppression

Provider cooling and runtime cooling should remain distinct.
