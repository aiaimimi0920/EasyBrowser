# scripts

Reserved for local helper scripts.

Typical future concerns:

- spawn smoke tests
- provider health probes
- runtime cleanup helpers

Current script:

Run smoke scripts one at a time. They currently all start `easybrowser.exe` on the default local listener `127.0.0.1:18080`.

- `smoke-test.ps1`
  - builds the Go parent binary if needed
  - starts the parent service
  - submits one strategy-routed execution request
  - verifies task, provider, and runtime responses
- `smoke-chrome.ps1`
  - starts the parent service
  - exercises the real local chrome provider
  - verifies version / open tab / list pages / close target flow
- `smoke-camoufox.ps1`
  - requires local camoufox python package and fetched browser assets
  - starts the parent service
  - exercises the real local camoufox provider
  - verifies version / open tab / list pages / close target flow
- `smoke-browserbase.ps1`
  - requires `BROWSERBASE_API_KEY`
  - starts the parent service
  - exercises the real Browserbase provider
  - verifies list / create / get / release session flow
- `smoke-strategy-profiles.ps1`
  - starts the parent service
  - exercises strategy profiles on real local providers
  - verifies `stealth-first`, fallback from disabled `camoufox`, and `chrome-first`
  - task route output now includes structured score diagnostics, candidate breakdowns,
    recent route history, fallback history, rejection summaries, all-time and
    windowed route insights, provider health summaries, operational events, and
    the control-plane summary endpoint
