"""Unit tests for relative and absolute date resolution."""

from datetime import date, timedelta

from app.nlu.dates import resolve_date


def test_aaj() -> None:
    today = date.today()
    assert resolve_date("aaj") == today
    assert resolve_date("आज") == today
    assert resolve_date("today") == today


def test_kal_past_vs_future() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # Past indicators
    assert resolve_date("kal diya tha") == yesterday
    assert resolve_date("कल दिया था") == yesterday
    assert resolve_date("yesterday") == yesterday

    # Future / promise indicators
    assert resolve_date("kal dega") == tomorrow
    assert resolve_date("कल देगा") == tomorrow
    assert resolve_date("tomorrow") == tomorrow


def test_parso() -> None:
    today = date.today()
    day_before_yesterday = today - timedelta(days=2)
    day_after_tomorrow = today + timedelta(days=2)

    assert resolve_date("parso jama tha") == day_before_yesterday
    assert resolve_date("parso dega") == day_after_tomorrow


def test_weekdays() -> None:
    today = date.today()
    target_sunday = resolve_date("Sunday ko dega")
    assert target_sunday is not None
    # 6 is Sunday in Python weekday (0=Mon, 6=Sun)
    assert target_sunday.weekday() == 6
    assert target_sunday >= today
