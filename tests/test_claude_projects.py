# -*- coding: utf-8 -*-
"""Projects are folders inside fixed roots, addressed by name only."""

import os
from types import SimpleNamespace

import pytest

from watch_pc_controller.claude_projects import (
    BadProjectName,
    ProjectExists,
    UnknownProject,
    create_project,
    latest_session_id,
    list_conversations,
    list_projects,
    resolve_project,
)


@pytest.fixture
def roots(tmp_path):
    a, b = tmp_path / "Projects", tmp_path / "project"
    for folder in (a / "Robox", a / "Projector", b / "apple-watch-pc-controller", a / ".hidden"):
        folder.mkdir(parents=True)
    (a / "notes.txt").write_text("not a project", encoding="utf-8")
    return [str(a), str(b)]


def test_lists_folders_newest_activity_first(roots):
    activity = {"Robox": 300, "Projector": 100, "apple-watch-pc-controller": 200}
    found = list_projects(roots, last_activity=lambda path: activity[os.path.basename(path)])
    assert [p["name"] for p in found] == ["Robox", "apple-watch-pc-controller", "Projector"]
    assert all(os.path.isabs(p["path"]) for p in found)


def test_hidden_folders_and_files_are_not_projects(roots):
    names = {p["name"] for p in list_projects(roots, last_activity=lambda path: None)}
    assert ".hidden" not in names and "notes.txt" not in names


def test_projects_without_sessions_fall_back_to_folder_time(roots):
    found = list_projects(roots, last_activity=lambda path: None)
    assert all(isinstance(p["last_activity"], int) for p in found)


def test_resolve_finds_by_name_case_insensitively(roots):
    assert resolve_project("robox", roots).endswith("Robox")


def test_resolve_unknown(roots):
    with pytest.raises(UnknownProject):
        resolve_project("Nope", roots)


@pytest.mark.parametrize("name", ["..", "..\\Windows", "../etc", "C:\\", "a/b", "a\\b", "", " "])
def test_resolve_rejects_paths(roots, name):
    with pytest.raises((UnknownProject, BadProjectName)):
        resolve_project(name, roots)


def test_create_makes_the_folder_in_the_first_root(roots):
    path = create_project("portfolio site", roots)
    assert os.path.isdir(path)
    assert os.path.dirname(path) == roots[0]
    assert os.path.basename(path) == "portfolio-site"


def test_create_refuses_an_existing_name(roots):
    with pytest.raises(ProjectExists):
        create_project("Robox", roots)


@pytest.mark.parametrize("name", ["", "../x", "a/b", "x" * 80, "hello!"])
def test_create_refuses_bad_names(roots, name):
    with pytest.raises(BadProjectName):
        create_project(name, roots)


def fake_sessions(*rows):
    sessions = [SimpleNamespace(session_id=s, summary=t, custom_title=None, first_prompt=f"אמרתי {s}", last_modified=m)
                for s, t, m in rows]
    return lambda directory=None, limit=None: sessions[:limit]


def test_conversations_are_listed_with_titles():
    lister = fake_sessions(("s2", "Sleep timer", 200), ("s1", "Games page", 100))
    assert list_conversations("D:/p", lister=lister) == [
        {"session_id": "s2", "title": "Sleep timer", "first_prompt": "אמרתי s2", "last_modified": 200},
        {"session_id": "s1", "title": "Games page", "first_prompt": "אמרתי s1", "last_modified": 100},
    ]


def test_a_custom_title_wins_and_long_prompts_are_cut():
    row = SimpleNamespace(session_id="s1", summary="auto", custom_title="שעון שינה", first_prompt="א" * 200, last_modified=1)
    [conv] = list_conversations("D:/p", lister=lambda directory=None, limit=None: [row])
    assert conv["title"] == "שעון שינה" and len(conv["first_prompt"]) == 80


def test_latest_session_id():
    assert latest_session_id("D:/p", lister=fake_sessions(("s2", "a", 2), ("s1", "b", 1))) == "s2"
    assert latest_session_id("D:/p", lister=fake_sessions()) is None
