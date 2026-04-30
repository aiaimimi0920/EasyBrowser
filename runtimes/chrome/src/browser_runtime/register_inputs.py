from __future__ import annotations

import random

from selenium.webdriver.common.keys import Keys


def generate_name() -> tuple[str, str]:
    first = ['Neo', 'John', 'Sarah', 'Michael', 'Emma', 'David', 'James', 'Robert', 'Mary', 'William', 'Richard', 'Thomas', 'Charles', 'Christopher', 'Daniel', 'Matthew', 'Anthony', 'Mark', 'Donald', 'Steven', 'Paul', 'Andrew', 'Joshua', 'Kenneth', 'Kevin', 'Brian', 'George', 'Edward', 'Ronald', 'Timothy']
    last = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White']
    return random.choice(first), random.choice(last)


def generate_pwd(length=12) -> str:
    chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@*&'
    return ''.join(random.choice(chars) for _ in range(length)) + 'A1@'


def enter_birthday(driver) -> str:
    try:
        birthday_input = driver.switch_to.active_element
        birthday_input.send_keys('1')
        birthday_input.send_keys(Keys.TAB)
        birthday_input = driver.switch_to.active_element
        birthday_input.send_keys('1')
        birthday_input.send_keys(Keys.TAB)
        birthday_input = driver.switch_to.active_element
        birthday_input.send_keys('2000')
        birthday_input.send_keys(Keys.ENTER)
    except Exception:
        pass
    return '2000-01-01'
