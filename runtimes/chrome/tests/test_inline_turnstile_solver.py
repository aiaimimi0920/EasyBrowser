from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from browser_runtime import inline_turnstile_solver  # noqa: E402


class InlineTurnstileSolverTests(unittest.TestCase):
    def test_launch_options_prefer_explicit_solver_executable(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "TURNSTILE_SOLVER_EXECUTABLE_PATH": "/custom/chrome",
                "BROWSER_BINARY_PATH": "/usr/bin/chromium",
                "TURNSTILE_SOLVER_BROWSER_TYPE": "chromium",
            },
            clear=False,
        ):
            launch_options = inline_turnstile_solver._browser_launch_identity()

        self.assertEqual({"executable_path": "/custom/chrome"}, launch_options)

    def test_launch_options_fall_back_to_runtime_browser_binary(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "BROWSER_BINARY_PATH": "/usr/bin/chromium",
                "TURNSTILE_SOLVER_BROWSER_TYPE": "chromium",
            },
            clear=False,
        ):
            os.environ.pop("TURNSTILE_SOLVER_EXECUTABLE_PATH", None)
            launch_options = inline_turnstile_solver._browser_launch_identity()

        self.assertEqual({"executable_path": "/usr/bin/chromium"}, launch_options)

    def test_launch_options_use_channel_when_no_executable_is_available(self) -> None:
        with mock.patch.dict(os.environ, {"TURNSTILE_SOLVER_BROWSER_TYPE": "chromium"}, clear=False):
            os.environ.pop("TURNSTILE_SOLVER_EXECUTABLE_PATH", None)
            os.environ.pop("BROWSER_BINARY_PATH", None)
            launch_options = inline_turnstile_solver._browser_launch_identity()

        self.assertEqual({"channel": "chromium"}, launch_options)


if __name__ == "__main__":
    unittest.main()
