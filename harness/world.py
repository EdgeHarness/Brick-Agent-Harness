"""Deprecated office-demo compatibility exports.

Generic execution does not import this module.
"""
from harness.errors import ToolError
from domains.office_demo.world import (
    CALENDAR,
    DATE_RE,
    EMAILS,
    SIM_TODAY,
    SIM_TODAY_HUMAN,
    TIME_RE,
    World,
    _check_date,
    _check_time,
)

__all__ = [
    "CALENDAR",
    "DATE_RE",
    "EMAILS",
    "SIM_TODAY",
    "SIM_TODAY_HUMAN",
    "TIME_RE",
    "ToolError",
    "World",
    "_check_date",
    "_check_time",
]
