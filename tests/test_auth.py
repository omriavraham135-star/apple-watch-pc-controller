# -*- coding: utf-8 -*-
"""The pieces that decide who may call the API."""

import pytest

from watch_pc_controller.auth import RateLimiter, bearer_token, client_is_local


@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1", True),
    ("127.8.9.10", True),
    ("::1", True),
    ("::ffff:127.0.0.1", True),
    ("localhost", True),
    ("192.168.1.50", False),
    ("10.0.0.2", False),
    ("127.0.0.1.evil", False),
    ("", False),
    (None, False),
    ("testclient", False),
])
def test_client_is_local(host, expected):
    assert client_is_local(host) is expected


def test_bearer_token_reads_the_header():
    assert bearer_token({"authorization": "Bearer abc123"}) == "abc123"
    assert bearer_token({"authorization": "bearer   abc123  "}) == "abc123"


@pytest.mark.parametrize("headers", [
    {},
    {"authorization": ""},
    {"authorization": "Basic abc"},
    {"authorization": "Bearer "},
])
def test_bearer_token_absent(headers):
    assert bearer_token(headers) is None


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_rate_limiter_blocks_after_the_limit():
    clock = Clock()
    limiter = RateLimiter(limit=3, window_s=60, clock=clock)
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]
    assert limiter.allow("b") is True          # per key


def test_rate_limiter_forgets_old_attempts():
    clock = Clock()
    limiter = RateLimiter(limit=2, window_s=60, clock=clock)
    limiter.allow("a"); limiter.allow("a")
    assert limiter.allow("a") is False
    clock.now += 60.01
    assert limiter.allow("a") is True
