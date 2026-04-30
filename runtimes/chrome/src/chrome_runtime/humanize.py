from __future__ import annotations

import random
import time
from selenium.webdriver import ActionChains


def human_delay(min_s: float = 0.3, max_s: float = 1.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def human_mouse_jitter(driver, *, attempts: int = 3) -> None:
    try:
        actions = ActionChains(driver)
        for _ in range(attempts):
            x_off = random.randint(-80, 80)
            y_off = random.randint(-40, 40)
            actions.move_by_offset(x_off, y_off)
            actions.pause(random.uniform(0.05, 0.15))
        actions.perform()
    except Exception:
        pass


def human_type(element, text: str, *, per_char_delay: tuple[float, float] = (0.03, 0.10)) -> None:
    if len(text) > 60:
        element.send_keys(text)
        return
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(*per_char_delay))
