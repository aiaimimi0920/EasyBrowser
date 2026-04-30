from __future__ import annotations

import random
import time
import urllib.error
import urllib.request
from typing import Callable


def post(*, url: str, body: str, header: dict, proxy: str | None = None, get_opener_fn: Callable[..., any]) -> tuple[str, dict]:
    data = body.encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=header, method='POST')
    with get_opener_fn(proxy).open(req) as resp:
        resp_text = resp.read().decode('utf-8')
        resp_headers = dict(resp.headers)
        return resp_text, resp_headers


def put(*, url: str, body: str, header: dict, proxy: str | None = None, get_opener_fn: Callable[..., any]) -> tuple[str, dict]:
    data = body.encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=header, method='PUT')
    with get_opener_fn(proxy).open(req) as resp:
        resp_text = resp.read().decode('utf-8')
        resp_headers = dict(resp.headers)
        return resp_text, resp_headers


def get(*, url: str, headers: dict | None = None, proxy: str | None = None, get_opener_fn: Callable[..., any]) -> tuple[str, dict]:
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with get_opener_fn(proxy).open(req) as response:
                resp_text = response.read().decode('utf-8')
                resp_headers = dict(response.getheaders())
                return resp_text, resp_headers
        except urllib.error.HTTPError as e:
            if e.code in (401, 429):
                raise
            delay = random.uniform(5, 10) + (i * 2)
            print(f'GET Request HTTPError: {e.code} for {url} - Retrying in {delay:.1f}s')
            time.sleep(delay)
        except Exception as e:
            delay = random.uniform(5, 10) + (i * 2)
            print(f'GET Request error: {e} - Retrying in {delay:.1f}s')
            time.sleep(delay)
    raise RuntimeError(f'Failed to GET {url} after retries')
