from __future__ import annotations

import unittest
from unittest import mock

from browser_runtime import driver_factory


class BrowserProfileCleanupTests(unittest.TestCase):
    def test_cleanup_keeps_other_browser_drivers_alive(self) -> None:
        processes = (
            "101 /usr/bin/chromedriver --port=51001\n"
            "102 /usr/bin/chrome --user-data-dir=/tmp/active-profile\n"
            "103 /usr/bin/chrome --user-data-dir=/tmp/stale-profile\n"
        ).encode()
        with mock.patch.object(driver_factory.signal, "SIGKILL", 9, create=True), mock.patch.object(
            driver_factory.os, "name", "posix",
        ), mock.patch.object(
            driver_factory.os, "getpid", return_value=1000,
        ), mock.patch.object(driver_factory, "env_flag", return_value=True), mock.patch.object(
            driver_factory, "_remove_browser_state_path", return_value=False,
        ), mock.patch.object(driver_factory.subprocess, "check_output", return_value=processes), mock.patch.object(
            driver_factory.os, "kill",
        ) as kill:
            driver_factory._cleanup_stale_browser_startup_state("/tmp/stale-profile")
        kill.assert_called_once_with(103, 9)

    def test_disabled_cleanup_does_not_touch_files_or_processes(self) -> None:
        with mock.patch.object(driver_factory, "env_flag", return_value=False), mock.patch.object(
            driver_factory, "_remove_browser_state_path",
        ) as remove, mock.patch.object(driver_factory.subprocess, "check_output") as processes:
            driver_factory._cleanup_stale_browser_startup_state("/tmp/profile")
        remove.assert_not_called()
        processes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
