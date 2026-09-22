# -*- coding: utf-8 -*-
"""Characterisation tests for the Hebrew command parser.

These pin down what the parser does today, so the behaviour cannot drift
unnoticed while the app grows around it. Two cases are marked xfail: they are
genuine defects, documented here rather than silently tolerated.
"""

import pytest

from watch_pc_controller.nlp_parser import parse_voice_command


# --------------------------------------------------------------- mute / unmute

@pytest.mark.parametrize("phrase", ["תשתיק", "השתק", "שקט", "בלי קול", "mute"])
def test_mute_phrases(phrase):
    result = parse_voice_command(phrase)

    assert result["intent"] == "mute"
    assert result["value"] is True


@pytest.mark.parametrize("phrase", ["בטל השתקה", "תחזיר קול", "unmute"])
def test_unmute_phrases(phrase):
    result = parse_voice_command(phrase)

    assert result["intent"] == "mute"
    assert result["value"] is False


def test_unmute_is_checked_before_mute():
    """'בטל השתקה' contains 'השתקה'; the negation has to win."""
    assert parse_voice_command("בטל השתקה")["value"] is False


# ------------------------------------------------------------------- relative

@pytest.mark.parametrize("phrase,delta", [
    ("תנמיך ב-50 אחוז", -50),
    ("תגביר ב-20 אחוז", 20),
    ("תרד ב-15", -15),
    ("תנמיך 20 אחוז", -20),
])
def test_relative_changes(phrase, delta):
    result = parse_voice_command(phrase)

    assert result["intent"] == "change_relative"
    assert result["delta"] == delta


@pytest.mark.parametrize("phrase,delta", [("תנמיך", -10), ("תגביר", 10)])
def test_bare_direction_steps_by_ten(phrase, delta):
    result = parse_voice_command(phrase)

    assert result["intent"] == "change_relative"
    assert result["delta"] == delta


# ------------------------------------------------------------------- absolute

@pytest.mark.parametrize("phrase,target", [
    ("תנמיך ל-50 אחוז", 50),
    ("תגביר ל-80 אחוז", 80),
    ("שים על 70", 70),
    ("כוון ל 30", 30),
    ("ווליום 60", 60),
])
def test_absolute_targets(phrase, target):
    result = parse_voice_command(phrase)

    assert result["intent"] == "set_absolute"
    assert result["target"] == target


@pytest.mark.parametrize("phrase,target", [
    ("עד הסוף", 100),
    ("מקסימום", 100),
    ("ווליום מלא", 100),
    ("על חצי", 50),
    ("חצי ווליום", 50),
])
def test_keyword_shortcuts(phrase, target):
    result = parse_voice_command(phrase)

    assert result["intent"] == "set_absolute"
    assert result["target"] == target


def test_relative_wins_over_absolute_when_both_markers_appear():
    """'ב-' is tested first, so it decides."""
    assert parse_voice_command("תנמיך ב-30 אחוז")["intent"] == "change_relative"


# -------------------------------------------------------------------- unknown

@pytest.mark.parametrize("phrase", ["בלה בלה", "", "מה השעה"])
def test_unrecognised_input(phrase):
    result = parse_voice_command(phrase)

    assert result["intent"] == "unknown"
    assert result["feedback"]


# ------------------------------------------------------------- known defects

@pytest.mark.xfail(
    reason="'חמישים' contains the substring 'שים', which the absolute-intent "
           "keyword check matches, flipping a relative command to absolute",
    strict=True,
)
def test_attached_prefix_with_hebrew_number_should_stay_relative():
    result = parse_voice_command("תנמיך בחמישים")

    assert result["intent"] == "change_relative"
    assert result["delta"] == -50


@pytest.mark.xfail(
    reason="the absolute regex requires 'ל-' or 'ל ', so a Hebrew number word "
           "fused to the prefix ('לשמונים') is read as relative",
    strict=True,
)
def test_fused_lamed_prefix_should_be_absolute():
    result = parse_voice_command("תגביר לשמונים")

    assert result["intent"] == "set_absolute"
    assert result["target"] == 80
