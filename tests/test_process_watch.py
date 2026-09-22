import os

import psutil

from watch_pc_controller.process_watch import focus_pid, running_pids


def current_process_name():
    return psutil.Process(os.getpid()).name()


def test_finds_a_process_that_is_definitely_running():
    """This test is itself a running process, so it is its own fixture."""
    found = running_pids([current_process_name()])

    assert current_process_name().lower() in found
    assert found[current_process_name().lower()] > 0


def test_matching_ignores_case():
    name = current_process_name()

    assert running_pids([name.upper()]) == running_pids([name.lower()])


def test_unknown_names_are_simply_absent():
    found = running_pids(["definitely-not-a-real-process.exe"])

    assert found == {}


def test_mixed_names_return_only_the_live_ones():
    found = running_pids([current_process_name(), "nope-not-running.exe"])

    assert current_process_name().lower() in found
    assert "nope-not-running.exe" not in found


def test_empty_request_does_no_work():
    assert running_pids([]) == {}
    assert running_pids(["", None]) == {}


def test_focusing_nothing_is_a_quiet_no():
    """A missing pid must return False rather than raise into the request."""
    assert focus_pid(None) is False
    assert focus_pid(0) is False


def test_focusing_a_pid_with_no_windows_returns_false():
    # A pid far above the plausible range owns no windows.
    assert focus_pid(999_999_999) is False
