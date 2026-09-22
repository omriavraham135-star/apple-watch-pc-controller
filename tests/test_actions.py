import json

import pytest

from watch_pc_controller.actions import ActionRegistry, UnknownActionError


VALID_CONFIG = [
    {"id": "screenshot", "label": "צילום מסך", "icon": "camera", "command": "nircmd savescreenshot"},
    {"id": "chrome", "label": "Chrome", "icon": "globe", "command": "start chrome"},
]


def write_config(tmp_path, payload, raw=None):
    path = tmp_path / "actions.json"
    path.write_text(raw if raw is not None else json.dumps(payload), encoding="utf-8")
    return path


class RecordingRunner:
    """Stands in for the real subprocess call so tests never spawn anything."""

    def __init__(self):
        self.calls = []

    def __call__(self, command):
        self.calls.append(command)


def test_lists_actions_from_config(tmp_path):
    registry = ActionRegistry(write_config(tmp_path, VALID_CONFIG), runner=RecordingRunner())

    listed = registry.list_actions()

    assert [a["id"] for a in listed] == ["screenshot", "chrome"]
    assert listed[0]["label"] == "צילום מסך"
    assert listed[0]["icon"] == "camera"


def test_listing_never_exposes_the_command(tmp_path):
    """The watch shows labels. Leaking commands would hand an attacker the payload."""
    registry = ActionRegistry(write_config(tmp_path, VALID_CONFIG), runner=RecordingRunner())

    for action in registry.list_actions():
        assert "command" not in action


def test_running_a_known_id_executes_its_configured_command(tmp_path):
    runner = RecordingRunner()
    registry = ActionRegistry(write_config(tmp_path, VALID_CONFIG), runner=runner)

    result = registry.run("chrome")

    assert runner.calls == ["start chrome"]
    assert result["id"] == "chrome"
    assert result["label"] == "Chrome"


def test_unknown_id_is_rejected_and_runs_nothing(tmp_path):
    runner = RecordingRunner()
    registry = ActionRegistry(write_config(tmp_path, VALID_CONFIG), runner=runner)

    with pytest.raises(UnknownActionError):
        registry.run("rm-rf")

    assert runner.calls == []


def test_a_command_string_is_never_accepted_as_an_id(tmp_path):
    """Guards the core property: the network supplies an id, never a command."""
    runner = RecordingRunner()
    registry = ActionRegistry(write_config(tmp_path, VALID_CONFIG), runner=runner)

    with pytest.raises(UnknownActionError):
        registry.run("start calc")

    assert runner.calls == []


def test_missing_config_file_yields_an_empty_registry(tmp_path):
    registry = ActionRegistry(tmp_path / "does-not-exist.json", runner=RecordingRunner())

    assert registry.list_actions() == []


def test_malformed_json_yields_an_empty_registry(tmp_path):
    registry = ActionRegistry(
        write_config(tmp_path, None, raw="{not json at all"), runner=RecordingRunner()
    )

    assert registry.list_actions() == []


def test_entries_missing_required_fields_are_skipped(tmp_path):
    config = [
        {"id": "good", "label": "Good", "command": "echo ok"},
        {"id": "no-command", "label": "Broken"},
        {"label": "no-id", "command": "echo nope"},
        "not-even-an-object",
    ]
    registry = ActionRegistry(write_config(tmp_path, config), runner=RecordingRunner())

    assert [a["id"] for a in registry.list_actions()] == ["good"]


def test_icon_defaults_when_absent(tmp_path):
    config = [{"id": "plain", "label": "Plain", "command": "echo hi"}]
    registry = ActionRegistry(write_config(tmp_path, config), runner=RecordingRunner())

    assert registry.list_actions()[0]["icon"] == "bolt"


def test_duplicate_ids_keep_the_first_entry(tmp_path):
    config = [
        {"id": "dup", "label": "First", "command": "echo first"},
        {"id": "dup", "label": "Second", "command": "echo second"},
    ]
    runner = RecordingRunner()
    registry = ActionRegistry(write_config(tmp_path, config), runner=runner)

    registry.run("dup")

    assert runner.calls == ["echo first"]
    assert len(registry.list_actions()) == 1


def test_reload_picks_up_an_edited_file(tmp_path):
    path = write_config(tmp_path, VALID_CONFIG)
    registry = ActionRegistry(path, runner=RecordingRunner())

    path.write_text(json.dumps([{"id": "new", "label": "New", "command": "echo new"}]), encoding="utf-8")
    registry.reload()

    assert [a["id"] for a in registry.list_actions()] == ["new"]


# ------------------------------------------------- knowing what is already up

PROCESS_CONFIG = [
    {"id": "chrome", "label": "Chrome", "command": "start chrome", "process": "chrome.exe"},
    {"id": "notes", "label": "Notes", "command": "start notepad", "process": "notepad.exe"},
    {"id": "shot", "label": "Screenshot", "command": "explorer ms-screenclip:"},
]


class FakeProber:
    """Stands in for scanning the real process table."""

    def __init__(self, running=()):
        self.running = {n.lower(): 1000 + i for i, n in enumerate(running)}
        self.queries = []

    def __call__(self, names):
        self.queries.append(sorted(n.lower() for n in names))
        return dict(self.running)


class FakeFocuser:
    def __init__(self, succeeds=True):
        self.succeeds = succeeds
        self.calls = []

    def __call__(self, pid):
        self.calls.append(pid)
        return self.succeeds


def registry(tmp_path, running=(), focus_works=True, config=None):
    prober = FakeProber(running)
    focuser = FakeFocuser(focus_works)
    runner = RecordingRunner()
    reg = ActionRegistry(
        write_config(tmp_path, config or PROCESS_CONFIG),
        runner=runner,
        prober=prober,
        focuser=focuser,
    )
    return reg, runner, prober, focuser


def test_listing_reports_which_process_an_action_watches(tmp_path):
    reg, _, _, _ = registry(tmp_path)

    by_id = {a["id"]: a for a in reg.list_actions()}

    assert by_id["chrome"]["process"] == "chrome.exe"
    assert by_id["shot"]["process"] is None


def test_status_reports_running_state_per_action(tmp_path):
    reg, _, _, _ = registry(tmp_path, running=["chrome.exe"])

    status = reg.statuses()

    assert status["chrome"]["running"] is True
    assert status["chrome"]["pid"] > 0
    assert status["notes"]["running"] is False
    assert status["notes"]["pid"] is None


def test_actions_without_a_process_are_never_reported_as_running(tmp_path):
    reg, _, _, _ = registry(tmp_path, running=["chrome.exe"])

    assert reg.statuses()["shot"]["running"] is False


def test_status_scans_the_process_table_once_for_all_actions(tmp_path):
    """One sweep, not one per tile — this is polled."""
    reg, _, prober, _ = registry(tmp_path, running=["chrome.exe"])

    reg.statuses()

    assert len(prober.queries) == 1
    assert prober.queries[0] == ["chrome.exe", "notepad.exe"]


def test_running_app_is_focused_rather_than_launched_again(tmp_path):
    reg, runner, _, focuser = registry(tmp_path, running=["chrome.exe"])

    result = reg.run("chrome")

    assert result["status"] == "focused"
    assert focuser.calls, "should have tried to raise the window"
    assert runner.calls == [], "must not launch a second copy"


def test_app_that_is_not_running_is_launched(tmp_path):
    reg, runner, _, focuser = registry(tmp_path, running=[])

    result = reg.run("chrome")

    assert result["status"] == "launched"
    assert runner.calls == ["start chrome"]
    assert focuser.calls == [], "nothing to focus"


def test_launch_is_the_fallback_when_the_window_will_not_come_forward(tmp_path):
    """Focus can fail for reasons out of our control; the tap must still do something."""
    reg, runner, _, focuser = registry(tmp_path, running=["chrome.exe"], focus_works=False)

    result = reg.run("chrome")

    assert focuser.calls, "should have attempted the focus first"
    assert result["status"] == "launched"
    assert runner.calls == ["start chrome"]


def test_actions_without_a_process_always_just_run(tmp_path):
    reg, runner, _, focuser = registry(tmp_path, running=["chrome.exe"])

    result = reg.run("shot")

    assert result["status"] == "launched"
    assert focuser.calls == []
    assert runner.calls == ["explorer ms-screenclip:"]


def test_a_blank_process_field_is_ignored(tmp_path):
    config = [{"id": "x", "label": "X", "command": "echo x", "process": "   "}]
    reg, runner, _, _ = registry(tmp_path, running=[], config=config)

    assert reg.list_actions()[0]["process"] is None
    assert reg.run("x")["status"] == "launched"
