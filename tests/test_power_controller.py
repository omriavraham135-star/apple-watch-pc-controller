import pytest

from watch_pc_controller.power_controller import (
    PowerController,
    UnknownPowerActionError,
)


class RecordingRunner:
    """Stands in for the real call so the test machine never actually shuts down."""

    def __init__(self):
        self.calls = []

    def __call__(self, command):
        self.calls.append(command)


def test_exposes_the_four_supported_actions():
    controller = PowerController(runner=RecordingRunner())

    assert set(controller.available_actions()) == {"lock", "sleep", "restart", "shutdown"}


@pytest.mark.parametrize("action", ["lock", "sleep", "restart", "shutdown"])
def test_each_action_dispatches_exactly_one_command(action):
    runner = RecordingRunner()
    controller = PowerController(runner=runner)

    result = controller.execute(action)

    assert len(runner.calls) == 1
    assert result["action"] == action


def test_lock_uses_the_windows_lock_workstation_call():
    runner = RecordingRunner()
    PowerController(runner=runner).execute("lock")

    assert "LockWorkStation" in " ".join(runner.calls[0])


def test_shutdown_and_restart_are_distinct_commands():
    runner = RecordingRunner()
    controller = PowerController(runner=runner)

    controller.execute("shutdown")
    controller.execute("restart")

    assert runner.calls[0] != runner.calls[1]


def test_unknown_action_is_rejected_and_runs_nothing():
    runner = RecordingRunner()
    controller = PowerController(runner=runner)

    with pytest.raises(UnknownPowerActionError):
        controller.execute("format-c")

    assert runner.calls == []


def test_restart_and_shutdown_are_marked_destructive():
    """The UI reads this to decide which buttons need press-and-hold."""
    controller = PowerController(runner=RecordingRunner())

    assert controller.is_destructive("shutdown") is True
    assert controller.is_destructive("restart") is True
    assert controller.is_destructive("lock") is False
    assert controller.is_destructive("sleep") is False


def test_describe_lists_actions_with_their_destructive_flag():
    controller = PowerController(runner=RecordingRunner())

    described = {a["action"]: a for a in controller.describe()}

    assert described["shutdown"]["destructive"] is True
    assert described["lock"]["destructive"] is False
    assert described["lock"]["label"]


# ---------------------------------------------------- accidental-touch guard

def test_harmless_actions_need_no_hold():
    """A lock or a sleep costs nothing if triggered by accident."""
    controller = PowerController(runner=RecordingRunner())

    assert controller.hold_seconds("lock") == 0
    assert controller.hold_seconds("sleep") == 0


def test_destructive_actions_are_graduated_by_consequence():
    """Losing unsaved work deserves a longer press than losing a session."""
    controller = PowerController(runner=RecordingRunner())

    assert controller.hold_seconds("restart") >= 2
    assert controller.hold_seconds("shutdown") > controller.hold_seconds("restart")


def test_every_destructive_action_requires_a_hold():
    controller = PowerController(runner=RecordingRunner())

    for entry in controller.describe():
        if entry["destructive"]:
            assert entry["hold_seconds"] > 0, f"{entry['action']} is unguarded"
        else:
            assert entry["hold_seconds"] == 0


def test_hold_seconds_rejects_unknown_actions():
    controller = PowerController(runner=RecordingRunner())

    with pytest.raises(UnknownPowerActionError):
        controller.hold_seconds("nope")


def test_describe_carries_the_hold_duration():
    controller = PowerController(runner=RecordingRunner())
    described = {a["action"]: a for a in controller.describe()}

    assert described["shutdown"]["hold_seconds"] == 3.0
    assert described["lock"]["hold_seconds"] == 0.0
