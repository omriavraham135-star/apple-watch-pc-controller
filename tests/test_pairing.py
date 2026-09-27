# -*- coding: utf-8 -*-
"""Pairing: a code shown on the PC buys one device a long-lived token."""

import json

import pytest

from watch_pc_controller.pairing import (
    CODE_TTL_SECONDS,
    MAX_CODE_ATTEMPTS,
    PairingError,
    PairingStore,
)


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return PairingStore(str(tmp_path / "devices.json"), clock=clock)


def test_code_is_six_digits(store):
    code = store.create_code()
    assert len(code) == 6 and code.isdigit()


def test_redeem_returns_a_token_that_verifies(store):
    token = store.redeem(store.create_code(), "Apple Watch")
    device = store.verify(token)
    assert device is not None
    assert device.name == "Apple Watch"


def test_a_code_pairs_only_one_device(store):
    code = store.create_code()
    store.redeem(code, "first")
    with pytest.raises(PairingError):
        store.redeem(code, "second")


def test_code_expires(store, clock):
    code = store.create_code()
    clock.now += CODE_TTL_SECONDS + 0.001
    with pytest.raises(PairingError):
        store.redeem(code, "late")


def test_wrong_code_is_rejected(store):
    store.create_code()
    with pytest.raises(PairingError):
        store.redeem("000000" if store._code != "000000" else "111111", "guess")


def test_too_many_wrong_attempts_burn_the_code(store):
    code = store.create_code()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(MAX_CODE_ATTEMPTS):
        with pytest.raises(PairingError):
            store.redeem(wrong, "guess")
    with pytest.raises(PairingError):
        store.redeem(code, "now too late")


def test_unknown_or_missing_token_does_not_verify(store):
    assert store.verify(None) is None
    assert store.verify("") is None
    assert store.verify("not-a-real-token") is None


def test_only_the_hash_is_written_to_disk(store, tmp_path):
    token = store.redeem(store.create_code(), "watch")
    text = (tmp_path / "devices.json").read_text(encoding="utf-8")
    assert token not in text


def test_devices_survive_a_restart(store, tmp_path, clock):
    token = store.redeem(store.create_code(), "watch")
    again = PairingStore(str(tmp_path / "devices.json"), clock=clock)
    assert again.verify(token) is not None


def test_revoke_stops_the_token(store):
    token = store.redeem(store.create_code(), "watch")
    device_id = store.verify(token).id
    assert store.revoke(device_id) is True
    assert store.verify(token) is None
    assert store.revoke(device_id) is False


def test_list_devices_never_exposes_the_hash(store):
    store.redeem(store.create_code(), "watch")
    listed = store.list_devices()
    assert len(listed) == 1
    assert set(listed[0]) == {"id", "name", "paired_at", "last_seen"}


def test_corrupt_file_starts_empty(tmp_path, clock):
    path = tmp_path / "devices.json"
    path.write_text("{ this is not json", encoding="utf-8")
    store = PairingStore(str(path), clock=clock)
    assert store.list_devices() == []


def test_long_device_names_are_trimmed(store):
    token = store.redeem(store.create_code(), "x" * 500)
    assert len(store.verify(token).name) == 40


def test_file_is_valid_json_after_pairing(store, tmp_path):
    store.redeem(store.create_code(), "watch")
    data = json.loads((tmp_path / "devices.json").read_text(encoding="utf-8"))
    assert isinstance(data, list) and data[0]["name"] == "watch"
