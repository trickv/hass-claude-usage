"""Verify the credit grant is found by its fields, whatever its key."""

import importlib.util
from pathlib import Path

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "hass_claude_usage"


def _load_credit():
    spec = importlib.util.spec_from_file_location("credit", COMPONENT_DIR / "credit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GRANT = {
    "utilization": 60.0,
    "resets_at": "2026-01-15T08:00:00+00:00",
    "limit_dollars": 100,
    "used_dollars": 59.994952,
    "remaining_dollars": 40.005048000000002,
    "locked_reason": None,
}


def test_grant_parsed_under_any_key():
    credit = _load_credit()
    for key in ("iguana_necktie", "some_future_codename"):
        assert credit.parse_credit({"five_hour": None, key: GRANT}) == {
            "credit_remaining": 40.01,
            "credit_limit": 100,
            "credit_reset_time": "2026-01-15T08:00:00+00:00",
        }


WINDOW = {
    "utilization": 8.0,
    "resets_at": "2026-11-09T23:50:00+00:00",
    "limit_dollars": None,
    "used_dollars": None,
    "remaining_dollars": None,
    "locked_reason": None,
}


def test_grant_found_after_windows_with_null_dollars():
    credit = _load_credit()
    raw = {"five_hour": WINDOW, "seven_day": WINDOW, "iguana_necktie": GRANT}
    assert credit.parse_credit(raw)["credit_limit"] == 100


def test_windows_with_null_dollars_are_not_a_grant():
    credit = _load_credit()
    raw = {"five_hour": WINDOW, "seven_day": WINDOW, "iguana_necktie": None}
    assert credit.parse_credit(raw) == {}


def test_no_grant_leaves_sensors_unavailable():
    credit = _load_credit()
    assert credit.parse_credit({"five_hour": {"utilization": 1}, "tangelo": None}) == {}
    assert credit.parse_credit({"spend": {"used": {"amount_minor": 0}}}) == {}
