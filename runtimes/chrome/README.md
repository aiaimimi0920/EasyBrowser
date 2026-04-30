# chrome

This repository is the new home for the **legacy anonymous Chrome runtime** migrated from:

- `C:\Users\Public\nas_home\AI\GameEditor\NeuroPlugin\infinite_refill\server\services\python_browser_service\src\browser_runtime\...`

## Target structure (initial)

```
repos/chrome/
  src/
    browser_runtime/
      __init__.py
      driver_factory.py           # migrated bootstrap, proxy extension, profile cleanup
      stealth_source.py           # migrated stealth JS source builder
      migrated_stealth_scripts.py # migrated stealth payload library
      stealth_helpers.py          # migrated helper utilities
      cdp_sourceurl.py
      browser_debug.py
      wait_utils.py
      humanize.py
      camoufox_native.py
      proxy_extension.py          # proxy extension utilities (wrapper)
      profile_manager.py          # profile lifecycle helpers (wrapper)
      runtime_entry.py            # runtime entrypoint (wrapper)
    shared_proxy/
      __init__.py
      system_native.py
```

## Ownership

- This repo owns **anonymous Chrome runtime behavior** (bootstrap, stealth, proxy/profile).
- Business-flow orchestration (register/repair composition) stays in NeuroPlugin.

## Dependencies

Python runtime dependencies (install in the environment used by EasyBrowser to spawn this runtime):

```
pip install -r requirements.txt
```
```

This repo is now actively being populated as part of the migration.
