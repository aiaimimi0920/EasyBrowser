from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from browser_runtime import turnstile_runtime  # noqa: E402


class _Driver:
    def __init__(self, payload):
        self._payload = payload
        self.script = ""
        self.calls = 0

    def execute_script(self, script: str):
        self.script = script
        self.calls += 1
        return self._payload


class TurnstileRuntimeTests(unittest.TestCase):
    def test_extract_turnstile_task_script_handles_iframe_path_sitekey(self) -> None:
        driver = _Driver(None)
        task = turnstile_runtime.extract_turnstile_task(driver)
        self.assertIsNone(task)
        self.assertIn("pathSegments.find", driver.script)
        self.assertIn("^0x[0-9A-Za-z_-]{10,}$", driver.script)
        self.assertIn("performance.getEntriesByType('resource')", driver.script)

    def test_wait_for_turnstile_task_retries_until_payload_is_available(self) -> None:
        payloads = [
            None,
            None,
            {
                "websiteURL": "https://auth.openai.com/api/accounts/authorize",
                "websiteKey": "0x4AAAAAAADnPIDROrmt1Wwj",
                "action": "",
                "cData": "",
            },
        ]

        class _PollingDriver(_Driver):
            def execute_script(self, script: str):
                self.script = script
                self.calls += 1
                return payloads.pop(0) if payloads else None

        driver = _PollingDriver(None)
        with mock.patch.object(turnstile_runtime.time, "sleep", return_value=None):
            task = turnstile_runtime.wait_for_turnstile_task(
                driver,
                timeout_seconds=1.0,
                poll_interval_seconds=0.01,
            )
        self.assertIsNotNone(task)
        self.assertEqual("0x4AAAAAAADnPIDROrmt1Wwj", str((task or {}).get("websiteKey") or ""))
        self.assertGreaterEqual(driver.calls, 3)


if __name__ == "__main__":
    unittest.main()
