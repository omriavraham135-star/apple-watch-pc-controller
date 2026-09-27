# -*- coding: utf-8 -*-
"""The API refuses unpaired devices and lets paired ones in."""

import asyncio

import httpx
import pytest

from watch_pc_controller import server
from watch_pc_controller.auth import PAIR_ATTEMPTS_PER_MINUTE, RateLimiter
from watch_pc_controller.pairing import PairingStore

REMOTE = "192.168.1.50"
LOCAL = "127.0.0.1"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "pairing_store", PairingStore(str(tmp_path / "devices.json")))
    monkeypatch.setattr(server, "pair_limiter", RateLimiter(PAIR_ATTEMPTS_PER_MINUTE))


def call(method, path, host=REMOTE, token=None, json=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def go():
        transport = httpx.ASGITransport(app=server.app, client=(host, 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://pc") as client:
            return await client.request(method, path, headers=headers, json=json)

    return asyncio.run(go())


def pair_remote(name="Apple Watch"):
    code = call("POST", "/api/pair/code", host=LOCAL).json()["code"]
    return call("POST", "/api/pair", json={"code": code, "device_name": name}).json()["token"]


def test_remote_without_token_is_refused():
    assert call("GET", "/api/actions").status_code == 401


def test_local_without_token_is_allowed():
    assert call("GET", "/api/actions", host=LOCAL).status_code == 200


def test_pairing_lets_a_remote_device_in():
    token = pair_remote()
    assert call("GET", "/api/actions", token=token).status_code == 200


def test_a_made_up_token_is_refused():
    assert call("GET", "/api/actions", token="made-up").status_code == 401


def test_only_the_pc_can_mint_a_code():
    token = pair_remote()
    assert call("POST", "/api/pair/code").status_code == 401
    assert call("POST", "/api/pair/code", token=token).status_code == 403


def test_wrong_code_is_refused():
    call("POST", "/api/pair/code", host=LOCAL)
    res = call("POST", "/api/pair", json={"code": "abcdef", "device_name": "x"})
    assert res.status_code == 403


def test_pairing_attempts_are_rate_limited():
    codes = [call("POST", "/api/pair", json={"code": "000000", "device_name": "x"}).status_code
             for _ in range(PAIR_ATTEMPTS_PER_MINUTE + 1)]
    assert codes[-1] == 429


def test_revoked_device_is_refused():
    token = pair_remote()
    device_id = call("GET", "/api/devices", host=LOCAL).json()["devices"][0]["id"]
    assert call("DELETE", f"/api/devices/{device_id}", host=LOCAL).status_code == 200
    assert call("GET", "/api/actions", token=token).status_code == 401


def test_revoking_an_unknown_device_is_404():
    assert call("DELETE", "/api/devices/nope", host=LOCAL).status_code == 404


def test_devices_are_listed_only_on_the_pc():
    token = pair_remote()
    assert call("GET", "/api/devices", token=token).status_code == 403


@pytest.mark.parametrize("path", ["/pair", "/orb.js", "/watch-ui.js"])
def test_pages_a_device_needs_to_pair_stay_open(path):
    assert call("GET", path).status_code == 200


def test_preflight_is_not_blocked():
    res = call("OPTIONS", "/api/actions")
    assert res.status_code != 401
