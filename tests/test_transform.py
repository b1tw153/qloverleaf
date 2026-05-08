from typing import Any

import pytest
from lark import Token

from qloverleaf.exceptions import UnsupportedFeatureError
from qloverleaf.parser import parse
from qloverleaf.transform import (
    AroundPointFilter,
    BboxFilter,
    CompleteStatement,
    ElementType,
    Evaluator,
    ForeachStatement,
    ForStatement,
    IfStatement,
    OverpassTransformer,
    PolygonFilter,
    QueryStatement,
    TagKeyFilter,
    TagValueFilter,
    _parse_datetime,
    _unquote,
)


def _transform_query(text: str) -> Any:
    return OverpassTransformer().transform(parse(text))


def _first_filter(text: str) -> Any:
    return _transform_query(text).children[0].children[0].filters[0]


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------


def _datetime_token(s: str) -> Token:
    return Token("DATETIME", s)


def test_parse_datetime_squote() -> None:
    result = _parse_datetime(_datetime_token("'2024-03-12T11:03:25Z'"))
    assert result.year == 2024
    assert result.month == 3
    assert result.day == 12
    assert result.hour == 11
    assert result.minute == 3
    assert result.second == 25
    assert result.tzname() == "UTC"


def test_parse_datetime_dquote() -> None:
    result = _parse_datetime(_datetime_token('"2024-03-12T11:03:25Z"'))
    assert result.year == 2024
    assert result.month == 3
    assert result.day == 12
    assert result.hour == 11
    assert result.minute == 3
    assert result.second == 25
    assert result.tzname() == "UTC"


def test_parse_datetime_invalid_date() -> None:
    with pytest.raises(Exception):
        _parse_datetime(_datetime_token("'2024-13-13T23:05:18Z'"))


def test_parse_datetime_invalid_time() -> None:
    with pytest.raises(ValueError):
        _parse_datetime(_datetime_token("'2024-12-13T23:61:18Z'"))


# ---------------------------------------------------------------------------
# _unquote
# ---------------------------------------------------------------------------


def _string_token(s: str) -> Token:
    return Token("STRING", s)


def test_unquote_double_quotes() -> None:
    assert _unquote(_string_token('"hello"')) == "hello"


def test_unquote_single_quotes() -> None:
    assert _unquote(_string_token("'hello'")) == "hello"


def test_unquote_empty_double_quotes() -> None:
    assert _unquote(_string_token('""')) == ""


def test_unquote_empty_single_quotes() -> None:
    assert _unquote(_string_token("''")) == ""


def test_unquote_unquoted_passthrough() -> None:
    assert _unquote(_string_token("hello")) == "hello"


def test_unquote_mismatched_quotes_passthrough() -> None:
    assert _unquote(_string_token("\"hello'")) == "\"hello'"


def test_unquote_escape_newline() -> None:
    assert _unquote(_string_token(r'"foo\nbar"')) == "foo\nbar"


def test_unquote_escape_tab() -> None:
    assert _unquote(_string_token(r'"foo\tbar"')) == "foo\tbar"


def test_unquote_escape_backslash() -> None:
    assert _unquote(_string_token(r'"foo\\bar"')) == "foo\\bar"


def test_unquote_escape_double_quote() -> None:
    assert _unquote(_string_token(r'"foo\"bar"')) == 'foo"bar'


def test_unquote_escape_single_quote() -> None:
    assert _unquote(_string_token('"foo\\\'bar"')) == "foo'bar"


def test_unquote_unicode_escape() -> None:
    assert _unquote(_string_token(r'"A"')) == "A"


def test_unquote_unicode_escape_supplementary() -> None:
    assert _unquote(_string_token(r'"é"')) == "é"


def test_unquote_multiple_escapes() -> None:
    assert _unquote(_string_token(r'"foo\nbar\ttab"')) == "foo\nbar\ttab"


def test_unquote_too_short_passthrough() -> None:
    assert _unquote(_string_token('"')) == '"'


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_key
# ---------------------------------------------------------------------------


def test_tag_key_unquoted() -> None:
    f = _first_filter("node[amenity];")
    assert isinstance(f, TagKeyFilter)
    assert f.key == "amenity"


def test_tag_key_quoted() -> None:
    f = _first_filter('node["gnis:feature_id"];')
    assert isinstance(f, TagKeyFilter)
    assert f.key == "gnis:feature_id"


def test_tag_key_quoted_single() -> None:
    f = _first_filter("node['gnis:feature_id'];")
    assert isinstance(f, TagKeyFilter)
    assert f.key == "gnis:feature_id"


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_value
# ---------------------------------------------------------------------------


def test_tag_value_unquoted() -> None:
    f = _first_filter("node[amenity=parking];")
    assert isinstance(f, TagValueFilter)
    assert f.value == "parking"


def test_tag_value_quoted() -> None:
    f = _first_filter('node["addr:street"="Main Street"];')
    assert isinstance(f, TagValueFilter)
    assert f.value == "Main Street"


def test_tag_value_quoted_single() -> None:
    f = _first_filter("node['addr:street'='Main Street'];")
    assert isinstance(f, TagValueFilter)
    assert f.value == "Main Street"


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_value_regex / regex_case_insensitive
# ---------------------------------------------------------------------------


def test_tag_value_regex_simple() -> None:
    f = _first_filter('node[amenity~"parking|parking_space"];')
    assert isinstance(f, TagValueFilter)
    assert f.value == "parking|parking_space"


def test_tag_value_regex_simple_single_quoted() -> None:
    f = _first_filter("node[amenity~'parking|parking_space'];")
    assert isinstance(f, TagValueFilter)
    assert f.value == "parking|parking_space"


def test_tag_value_regex_case_sensitive() -> None:
    f = _first_filter('node[amenity~"parking|parking_space"];')
    assert isinstance(f, TagValueFilter)
    assert f.case_insensitive is False


def test_tag_value_regex_case_insensitive() -> None:
    f = _first_filter('node[amenity~"parking|parking_space",i];')
    assert isinstance(f, TagValueFilter)
    assert f.case_insensitive is True


# ---------------------------------------------------------------------------
# OverpassTransformer.around_radius
# ---------------------------------------------------------------------------

# (TODO)

# ---------------------------------------------------------------------------
# OverpassTransformer.bbox_filter
# ---------------------------------------------------------------------------


def test_bbox_filter_values() -> None:
    f = _first_filter("node(51.5,-0.2,51.6,-0.1);")
    assert isinstance(f, BboxFilter)
    assert f.south == "51.5"
    assert f.west == "-0.2"
    assert f.north == "51.6"
    assert f.east == "-0.1"


def test_bbox_filter_inverted_warns() -> None:
    transformer = OverpassTransformer()
    transformer.transform(parse("node(51.6,-0.2,51.5,-0.1);"))
    assert len(transformer.warnings) == 1
    assert "south >= north" in transformer.warnings[0].message


# ---------------------------------------------------------------------------
# OverpassTransformer.set_ref
# ---------------------------------------------------------------------------

# (TODO)

# ---------------------------------------------------------------------------
# OverpassTransformer.recurse_role
# ---------------------------------------------------------------------------

# (TODO)

# ---------------------------------------------------------------------------
# OverpassTransformer.int_range
# ---------------------------------------------------------------------------

# (TODO)

# ---------------------------------------------------------------------------
# OverpassTransformer.around_lat_lon (via around_point_filter)
# ---------------------------------------------------------------------------


def test_around_lat_lon_values() -> None:
    f = _first_filter("node(around:100.0,51.5,-0.2);")
    assert isinstance(f, AroundPointFilter)
    assert f.lat == "51.5"
    assert f.lon == "-0.2"


# ---------------------------------------------------------------------------
# OverpassTransformer.poly_lat_lon (via polygon_filter)
# ---------------------------------------------------------------------------


def test_poly_lat_lon_values() -> None:
    f = _first_filter('node(poly:"51.5 -0.2 51.6 -0.1 51.5 -0.3");')
    assert isinstance(f, PolygonFilter)
    assert f.points == [("51.5", "-0.2"), ("51.6", "-0.1"), ("51.5", "-0.3")]


# ---------------------------------------------------------------------------
# OverpassTransformer.query_stmt
# ---------------------------------------------------------------------------


def _query_stmt(text: str) -> QueryStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, QueryStatement)
    return stmt


def test_query_stmt_node() -> None:
    stmt = _query_stmt("node;")
    assert stmt.element_types == frozenset({ElementType.NODE})
    assert stmt.filters == []
    assert stmt.output_set is None


def test_query_stmt_way() -> None:
    stmt = _query_stmt("way;")
    assert stmt.element_types == frozenset({ElementType.WAY})


def test_query_stmt_relation() -> None:
    stmt = _query_stmt("relation;")
    assert stmt.element_types == frozenset({ElementType.RELATION})


def test_query_stmt_nwr() -> None:
    stmt = _query_stmt("nwr;")
    assert stmt.element_types == frozenset(
        {ElementType.NODE, ElementType.WAY, ElementType.RELATION}
    )


def test_query_stmt_nw() -> None:
    stmt = _query_stmt("nw;")
    assert stmt.element_types == frozenset({ElementType.NODE, ElementType.WAY})


def test_query_stmt_wr() -> None:
    stmt = _query_stmt("wr;")
    assert stmt.element_types == frozenset({ElementType.WAY, ElementType.RELATION})


def test_query_stmt_nr() -> None:
    stmt = _query_stmt("nr;")
    assert stmt.element_types == frozenset({ElementType.NODE, ElementType.RELATION})


def test_query_stmt_area() -> None:
    stmt = _query_stmt("area;")
    assert stmt.element_types == frozenset({ElementType.AREA})


def test_query_stmt_filters() -> None:
    stmt = _query_stmt("node[amenity=cafe](51.5,-0.2,51.6,-0.1);")
    assert len(stmt.filters) == 2
    assert isinstance(stmt.filters[0], TagValueFilter)
    assert isinstance(stmt.filters[1], BboxFilter)


def test_query_stmt_output_set() -> None:
    stmt = _query_stmt("node[amenity=cafe] -> .x;")
    assert stmt.output_set is not None
    assert stmt.output_set.name == "x"


def test_query_stmt_no_output_set() -> None:
    stmt = _query_stmt("node[amenity=cafe];")
    assert stmt.output_set is None


# ---------------------------------------------------------------------------
# OverpassTransformer.foreach_stmt
# ---------------------------------------------------------------------------


def _foreach_stmt(text: str) -> ForeachStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, ForeachStatement)
    return stmt


def test_foreach_default_input_set() -> None:
    stmt = _foreach_stmt("foreach { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None


def test_foreach_explicit_input_set() -> None:
    stmt = _foreach_stmt("foreach .x { node; }")
    assert stmt.input_set.name == "x"
    assert isinstance(stmt.input_set.token, Token)


def test_foreach_output_set() -> None:
    stmt = _foreach_stmt("foreach .x -> .y { node; }")
    assert stmt.output_set is not None
    assert stmt.output_set.name == "y"


def test_foreach_no_output_set() -> None:
    stmt = _foreach_stmt("foreach .x { node; }")
    assert stmt.output_set is None


def test_foreach_output_set_without_input() -> None:
    stmt = _foreach_stmt("foreach -> .y { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.output_set is not None
    assert stmt.output_set.name == "y"


def test_foreach_body() -> None:
    stmt = _foreach_stmt("foreach { node[amenity=cafe]; node[amenity=parking]; }")
    assert len(stmt.body) == 2


# ---------------------------------------------------------------------------
# OverpassTransformer.for_stmt
# ---------------------------------------------------------------------------


def _for_stmt(text: str) -> ForStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, ForStatement)
    return stmt


def test_for_default_input_set() -> None:
    stmt = _for_stmt("for(1) { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None


def test_for_explicit_input_set() -> None:
    stmt = _for_stmt("for .x (1) { node; }")
    assert stmt.input_set.name == "x"
    assert isinstance(stmt.input_set.token, Token)


def test_for_output_set() -> None:
    stmt = _for_stmt("for .x -> .y (1) { node; }")
    assert stmt.output_set is not None
    assert stmt.output_set.name == "y"


def test_for_no_output_set() -> None:
    stmt = _for_stmt("for .x (1) { node; }")
    assert stmt.output_set is None


def test_for_output_set_without_input() -> None:
    stmt = _for_stmt("for -> .y (1) { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.output_set is not None
    assert stmt.output_set.name == "y"


def test_for_evaluator() -> None:
    stmt = _for_stmt("for(1) { node; }")
    assert stmt.evaluator is not None


def test_for_body() -> None:
    stmt = _for_stmt("for(1) { node[amenity=cafe]; node[amenity=parking]; }")
    assert len(stmt.body) == 2


# ---------------------------------------------------------------------------
# OverpassTransformer.complete_stmt
# ---------------------------------------------------------------------------


def _complete_stmt(text: str) -> CompleteStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, CompleteStatement)
    return stmt


def test_complete_default_input_set() -> None:
    stmt = _complete_stmt("complete { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None


def test_complete_explicit_input_set() -> None:
    stmt = _complete_stmt("complete .x { node; }")
    assert stmt.input_set.name == "x"
    assert isinstance(stmt.input_set.token, Token)


def test_complete_output_set() -> None:
    stmt = _complete_stmt("complete .x -> .y { node; }")
    assert stmt.output_set is not None
    assert stmt.output_set.name == "y"


def test_complete_no_output_set() -> None:
    stmt = _complete_stmt("complete .x { node; }")
    assert stmt.output_set is None


def test_complete_output_set_without_input() -> None:
    stmt = _complete_stmt("complete -> .y { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.output_set is not None
    assert stmt.output_set.name == "y"


def test_complete_max_iterations() -> None:
    stmt = _complete_stmt("complete(5) { node; }")
    assert stmt.max_iterations == 5


def test_complete_no_max_iterations() -> None:
    stmt = _complete_stmt("complete { node; }")
    assert stmt.max_iterations is None


def test_complete_body() -> None:
    stmt = _complete_stmt("complete { node[amenity=cafe]; node[amenity=parking]; }")
    assert len(stmt.body) == 2


# ---------------------------------------------------------------------------
# OverpassTransformer.if_stmt
# ---------------------------------------------------------------------------


def _if_stmt(text: str) -> IfStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, IfStatement)
    return stmt


def test_if_condition() -> None:
    stmt = _if_stmt("if(1) { node; }")
    assert stmt.condition is not None
    assert isinstance(stmt.condition, Evaluator)


def test_if_then_body() -> None:
    stmt = _if_stmt("if(1) { node[amenity=cafe]; node[amenity=parking]; }")
    assert len(stmt.then_body) == 2


def test_if_no_else_body() -> None:
    stmt = _if_stmt("if(1) { node; }")
    assert stmt.else_body is None


def test_if_else_body() -> None:
    stmt = _if_stmt("if(1) { node[amenity=cafe]; } else { node[amenity=parking]; way; }")
    assert stmt.else_body is not None
    assert len(stmt.else_body) == 2


# ---------------------------------------------------------------------------
# OverpassTransformer.retro_stmt
# ---------------------------------------------------------------------------


def test_retro_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _transform_query("retro(1) { node; }")
