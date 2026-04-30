# browser_runtime

Migration target for the legacy anonymous Chrome runtime.

Source of truth:

- `C:\Users\Public\nas_home\AI\GameEditor\NeuroPlugin\infinite_refill\server\services\python_browser_service\src\browser_runtime`

This package keeps runtime/bootstrap/stealth/proxy behaviors, while business-flow orchestration stays in NeuroPlugin.

Included session primitives:

- `session_state.py` provides session container and history tracking without business-flow orchestration.
