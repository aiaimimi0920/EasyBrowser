# EasyBrowser Process Isolation

Core design assumption:

- browser-specific work should prefer isolated processes as the execution
  boundary

Why:

- message isolation
- better fault containment
- reduced cross-request interference
- higher availability when some runtimes become unhealthy

Current structural implications:

- `process-manager/` owns child process lifecycle
- `runtime-pool/` owns isolated runtime allocation
- `ipc/` owns parent/child communication shape
- `cooling/` and `stats/` can reason about failures at provider or runtime
  instance granularity
