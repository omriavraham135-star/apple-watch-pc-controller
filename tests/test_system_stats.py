from watch_pc_controller.system_stats import get_stats


def test_returns_the_three_metrics_the_watch_draws():
    stats = get_stats()

    assert set(["cpu", "memory", "disk"]).issubset(stats.keys())


def test_percentages_are_within_bounds():
    stats = get_stats()

    for key in ("cpu", "memory", "disk"):
        assert isinstance(stats[key], int), f"{key} should be a whole percent"
        assert 0 <= stats[key] <= 100, f"{key} out of range: {stats[key]}"


def test_reports_absolute_memory_and_disk_figures():
    stats = get_stats()

    assert stats["memory_total_gb"] > 0
    assert 0 <= stats["memory_used_gb"] <= stats["memory_total_gb"]
    assert stats["disk_total_gb"] > 0
    assert 0 <= stats["disk_free_gb"] <= stats["disk_total_gb"]


def test_reports_uptime():
    stats = get_stats()

    assert isinstance(stats["uptime_seconds"], int)
    assert stats["uptime_seconds"] >= 0


def test_consecutive_calls_stay_within_bounds():
    """cpu_percent has a priming quirk; a second call must still be sane."""
    get_stats()
    stats = get_stats()

    assert 0 <= stats["cpu"] <= 100
