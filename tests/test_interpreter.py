import pytest

from qloverleaf.exceptions import QueryError, UnsupportedFeatureError
from qloverleaf.interpreter import _apply_global_settings
from qloverleaf.parser import parse
from qloverleaf.query_context import Bbox, OutputFormat, QueryContext


def make_query(text: str) -> QueryContext:
    return QueryContext(text=text, tree=parse(text))


# ---------------------------------------------------------------------------
# timeout
# ---------------------------------------------------------------------------


def test_timeout_sets_value(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[timeout:25];out;")
    _apply_global_settings(query)
    assert query.timeout == 25


def test_timeout_default_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("out;")
    default = query.timeout
    _apply_global_settings(query)
    assert query.timeout == default


def test_timeout_duplicate_raises(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[timeout:25][timeout:30];out;")
    with pytest.raises(QueryError, match="Duplicate global timeout"):
        _apply_global_settings(query)


# ---------------------------------------------------------------------------
# maxsize
# ---------------------------------------------------------------------------


def test_maxsize_sets_value(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[maxsize:1000];out;")
    _apply_global_settings(query)
    assert query.maxsize == 1000


def test_maxsize_default_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("out;")
    default = query.maxsize
    _apply_global_settings(query)
    assert query.maxsize == default


def test_maxsize_duplicate_raises(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[maxsize:1000][maxsize:2000];out;")
    with pytest.raises(QueryError, match="Duplicate global maxsize"):
        _apply_global_settings(query)


# ---------------------------------------------------------------------------
# output format
# ---------------------------------------------------------------------------


def test_output_json(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[out:json];out;")
    _apply_global_settings(query)
    assert query.out == OutputFormat.JSON


def test_output_xml(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[out:xml];out;")
    _apply_global_settings(query)
    assert query.out == OutputFormat.XML


def test_output_csv(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[out:csv(::id)];out;")
    _apply_global_settings(query)
    assert query.out == OutputFormat.CSV


def test_output_default_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("out;")
    default = query.out
    _apply_global_settings(query)
    assert query.out == default


def test_output_duplicate_raises(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[out:json][out:xml];out;")
    with pytest.raises(QueryError, match="Duplicate global output"):
        _apply_global_settings(query)


# ---------------------------------------------------------------------------
# bbox
# ---------------------------------------------------------------------------


def test_bbox_sets_value(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[bbox:51.5,-0.2,51.6,-0.1];out;")
    _apply_global_settings(query)
    assert query.bbox == Bbox(south="51.5", west="-0.2", north="51.6", east="-0.1")


def test_bbox_default_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("out;")
    _apply_global_settings(query)
    assert query.bbox is None


def test_bbox_duplicate_raises(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[bbox:51.5,-0.2,51.6,-0.1][bbox:51.5,-0.2,51.6,-0.1];out;")
    with pytest.raises(QueryError, match="Duplicate global bbox"):
        _apply_global_settings(query)


def test_bbox_inverted_raises(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query("[bbox:51.6,-0.2,51.5,-0.1];out;")
    with pytest.raises(QueryError, match="Invalid global bbox"):
        _apply_global_settings(query)


# ---------------------------------------------------------------------------
# unsupported settings
# ---------------------------------------------------------------------------


def test_date_raises(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query('[date:"2024-01-01T00:00:00Z"];out;')
    with pytest.raises(UnsupportedFeatureError):
        _apply_global_settings(query)


def test_diff_raises(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query('[diff:"2024-01-01T00:00:00Z"];out;')
    with pytest.raises(UnsupportedFeatureError):
        _apply_global_settings(query)


def test_adiff_raises(capsys: pytest.CaptureFixture[str]) -> None:
    query = make_query('[adiff:"2024-01-01T00:00:00Z"];out;')
    with pytest.raises(UnsupportedFeatureError):
        _apply_global_settings(query)
