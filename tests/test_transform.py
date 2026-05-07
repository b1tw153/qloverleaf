import pytest
from lark import Token

from qloverleaf.transform import _parse_datetime

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def test_parse_datetime_squote() -> None:
    value = Token("DATETIME", "'2024-03-12T11:03:25Z'")
    result = _parse_datetime(value)
    assert result.year == 2024
    assert result.month == 3
    assert result.day == 12
    assert result.hour == 11
    assert result.minute == 3
    assert result.second == 25
    assert result.tzname() == "UTC"


def test_parse_datetime_dquote() -> None:
    value = Token("DATETIME", '"2024-03-12T11:03:25Z"')
    result = _parse_datetime(value)
    assert result.year == 2024
    assert result.month == 3
    assert result.day == 12
    assert result.hour == 11
    assert result.minute == 3
    assert result.second == 25
    assert result.tzname() == "UTC"


def test_parse_datetime_invalid_date() -> None:
    value = Token("DATETIME", "'2024-13-13T23:05:18Z'")
    with pytest.raises(Exception):
        _parse_datetime(value)


def test_parse_datetime_invalid_time() -> None:
    value = Token("DATETIME", "'2024-12-13T23:61:18Z'")
    with pytest.raises(ValueError):
        _parse_datetime(value)
