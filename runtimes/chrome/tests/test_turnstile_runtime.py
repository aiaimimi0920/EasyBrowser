from __future__ import annotations

import sys
import unittest
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from browser_runtime import turnstile_runtime  # noqa: E402


class _Driver:
    def __init__(self, payload):
        self._payload = payload
        self.script = ""

    def execute_script(self, script: str):
        self.script = script
        return self._payload


class TurnstileRuntimeTests(unittest.TestCase):
    def test_extract_turnstile_task_script_handles_iframe_path_sitekey(self) -> None:
        driver = _Driver(None)
        task = turnstile_runtime.extract_turnstile_task(driver)
        self.assertIsNone(task)
        self.assertIn("pathSegments.find", driver.script)
        self.assertIn("^0x[0-9A-Za-z_-]{10,}$", driver.script)


if __name__ == "__main__":
    unittest.main()
