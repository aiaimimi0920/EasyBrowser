import unittest
from unittest import mock

from selenium.webdriver.common.by import By

from browser_runtime import repairer_flow


class _FakeElement:
    def __init__(self) -> None:
        self.clicked = False

    def is_displayed(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True


class _FakeDriver:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.seen_xpaths: list[str] = []
        self.login_element = _FakeElement()

    def get(self, url: str) -> None:
        self.get_calls.append(url)

    def find_elements(self, by: str, value: str):
        if by == By.XPATH:
            self.seen_xpaths.append(value)
            if "Log In" in value or "Log in" in value:
                return [self.login_element]
        return []


class RepairerFlowCommunityLoginTests(unittest.TestCase):
    def test_community_start_url_is_recognized(self) -> None:
        self.assertTrue(repairer_flow._is_openai_community_url("https://community.openai.com/"))
        self.assertTrue(repairer_flow._is_openai_community_url("https://community.openai.com/latest"))
        self.assertFalse(repairer_flow._is_openai_community_url("https://auth.openai.com/log-in"))
        self.assertFalse(repairer_flow._is_openai_community_url("https://evil.example/community.openai.com/"))

    def test_community_login_trigger_clicks_discourse_login_cta(self) -> None:
        driver = _FakeDriver()
        clicked: list[_FakeElement] = []

        def click_with_debug(_driver, element, **_kwargs) -> None:
            element.clicked = True
            clicked.append(element)

        self.assertTrue(repairer_flow._trigger_openai_community_login(driver, click_with_debug=click_with_debug))
        self.assertEqual(clicked, [driver.login_element])
        self.assertTrue(driver.seen_xpaths)

    def test_open_start_url_clicks_community_login_when_auth_wait_fails_first(self) -> None:
        driver = _FakeDriver()
        clicked: list[_FakeElement] = []
        wait_seconds: list[int] = []
        primed: list[str] = []

        def click_with_debug(_driver, element, **_kwargs) -> None:
            element.clicked = True
            clicked.append(element)

        def wait_for_auth(seconds: int) -> None:
            wait_seconds.append(seconds)
            if len(wait_seconds) == 1:
                raise RuntimeError("not on auth yet")

        def prime_openai_environment(_driver) -> bool:
            primed.append("yes")
            return True

        repairer_flow._open_start_url_and_wait_for_auth(
            driver,
            "https://community.openai.com/",
            click_with_debug=click_with_debug,
            wait_for_auth=wait_for_auth,
            prime_openai_environment=prime_openai_environment,
        )

        self.assertEqual(driver.get_calls, ["https://community.openai.com/"])
        self.assertEqual(clicked, [driver.login_element])
        self.assertEqual(wait_seconds, [15, 60])
        self.assertEqual(primed, ["yes"])

    def test_open_start_url_does_not_prime_for_non_community_url(self) -> None:
        driver = _FakeDriver()
        primed: list[str] = []

        repairer_flow._open_start_url_and_wait_for_auth(
            driver,
            "https://auth.openai.com/log-in",
            click_with_debug=lambda *_args, **_kwargs: None,
            wait_for_auth=lambda _seconds: None,
            prime_openai_environment=lambda _driver: primed.append("yes") or True,
        )

        self.assertEqual(driver.get_calls, ["https://auth.openai.com/log-in"])
        self.assertEqual(primed, [])

    def test_prime_openai_auth_environment_uses_existing_chatgpt_bootstrap(self) -> None:
        driver = _FakeDriver()

        with mock.patch.object(repairer_flow, "generate_chatgpt_web_oauth_url", return_value=object()) as bootstrap:
            self.assertTrue(repairer_flow._prime_openai_auth_environment(driver))

        bootstrap.assert_called_once_with(driver=driver)

    def test_community_home_can_be_login_success_after_auth_flow(self) -> None:
        self.assertTrue(repairer_flow._is_logged_in_openai_web_url("https://community.openai.com/"))
        self.assertTrue(repairer_flow._is_logged_in_openai_web_url("https://community.openai.com/latest"))
        self.assertFalse(repairer_flow._is_logged_in_openai_web_url("https://community.openai.com/login"))
        self.assertFalse(repairer_flow._is_logged_in_openai_web_url("https://community.openai.com/auth/oidc/callback?code=1"))


if __name__ == "__main__":
    unittest.main()
