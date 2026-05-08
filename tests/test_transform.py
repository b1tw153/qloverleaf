from typing import Any

import pytest
from lark import Token

from qloverleaf.exceptions import UnimplementedFeatureError, UnsupportedFeatureError
from qloverleaf.parser import parse
from qloverleaf.transform import (
    AddExpression,
    AddOperator,
    AroundPointFilter,
    BboxFilter,
    BinaryExpression,
    BinaryOperator,
    CompareExpression,
    CompareOperator,
    CompleteStatement,
    CoordinateAxis,
    CoordinateExpression,
    ElementType,
    Evaluator,
    ForeachStatement,
    ForStatement,
    IfStatement,
    IsClosedExpression,
    IsTagExpression,
    LengthExpression,
    LiteralExpression,
    MetadataAttribute,
    MetadataExpression,
    MultiplyExpression,
    MultiplyOperator,
    OverpassTransformer,
    PolygonFilter,
    QueryStatement,
    TagKeyFilter,
    TagValueExpression,
    TagValueFilter,
    TernaryExpression,
    UnaryExpression,
    UnaryOperator,
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
    stmt = _if_stmt(
        "if(1) { node[amenity=cafe]; } else { node[amenity=parking]; way; }"
    )
    assert stmt.else_body is not None
    assert len(stmt.else_body) == 2


# ---------------------------------------------------------------------------
# OverpassTransformer.retro_stmt
# ---------------------------------------------------------------------------


def test_retro_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _transform_query("retro(1) { node; }")


# ---------------------------------------------------------------------------
# OverpassTransformer.ternary_expr
# ---------------------------------------------------------------------------


def _evaluator(expr: str) -> Any:
    return _for_stmt(f"for({expr}) {{ node; }}").evaluator


def test_ternary_expr() -> None:
    e = _evaluator("1 ? 2 : 3")
    assert isinstance(e, TernaryExpression)
    assert isinstance(e.condition, Evaluator)
    assert isinstance(e.true_expression, Evaluator)
    assert isinstance(e.false_expression, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.or_expr
# ---------------------------------------------------------------------------


def test_or_expr() -> None:
    e = _evaluator("1 || 0")
    assert isinstance(e, BinaryExpression)
    assert e.operator == BinaryOperator.OR
    assert len(e.operands) == 2


def test_or_expr_repeated() -> None:
    e = _evaluator("1 || 0 || 1")
    assert isinstance(e, BinaryExpression)
    assert e.operator == BinaryOperator.OR
    assert len(e.operands) == 3


# ---------------------------------------------------------------------------
# OverpassTransformer.and_expr
# ---------------------------------------------------------------------------


def test_and_expr() -> None:
    e = _evaluator("1 && 0")
    assert isinstance(e, BinaryExpression)
    assert e.operator == BinaryOperator.AND
    assert len(e.operands) == 2


def test_and_expr_repeated() -> None:
    e = _evaluator("1 && 0 && 1")
    assert isinstance(e, BinaryExpression)
    assert e.operator == BinaryOperator.AND
    assert len(e.operands) == 3


# ---------------------------------------------------------------------------
# OverpassTransformer.not_expr
# ---------------------------------------------------------------------------


def test_not_expr() -> None:
    e = _evaluator("!1")
    assert isinstance(e, UnaryExpression)
    assert e.operator == UnaryOperator.NOT
    assert isinstance(e.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.compare_expr
# ---------------------------------------------------------------------------


def test_compare_expr_equal() -> None:
    e = _evaluator("1 == 2")
    assert isinstance(e, CompareExpression)
    assert e.operator == CompareOperator.EQUAL


def test_compare_expr_not_equal() -> None:
    e = _evaluator("1 != 2")
    assert isinstance(e, CompareExpression)
    assert e.operator == CompareOperator.NOT_EQUAL


def test_compare_expr_less_than() -> None:
    e = _evaluator("1 < 2")
    assert isinstance(e, CompareExpression)
    assert e.operator == CompareOperator.LESS_THAN


def test_compare_expr_greater_than() -> None:
    e = _evaluator("1 > 2")
    assert isinstance(e, CompareExpression)
    assert e.operator == CompareOperator.GREATER_THAN


def test_compare_expr_less_than_or_equal() -> None:
    e = _evaluator("1 <= 2")
    assert isinstance(e, CompareExpression)
    assert e.operator == CompareOperator.LESS_THAN_OR_EQUAL


def test_compare_expr_greater_than_or_equal() -> None:
    e = _evaluator("1 >= 2")
    assert isinstance(e, CompareExpression)
    assert e.operator == CompareOperator.GREATER_THAN_OR_EQUAL


def test_compare_expr_operands() -> None:
    e = _evaluator("1 == 2")
    assert isinstance(e, CompareExpression)
    assert isinstance(e.left_operand, Evaluator)
    assert isinstance(e.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.add_expr
# ---------------------------------------------------------------------------


def test_add_expr_add() -> None:
    e = _evaluator("1 + 2")
    assert isinstance(e, AddExpression)
    assert e.operator == AddOperator.ADD


def test_add_expr_subtract() -> None:
    e = _evaluator("1 - 2")
    assert isinstance(e, AddExpression)
    assert e.operator == AddOperator.SUBTRACT


def test_add_expr_operands() -> None:
    e = _evaluator("1 + 2")
    assert isinstance(e, AddExpression)
    assert isinstance(e.left_operand, Evaluator)
    assert isinstance(e.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.mul_expr
# ---------------------------------------------------------------------------


def test_mul_expr_multiply() -> None:
    e = _evaluator("2 * 3")
    assert isinstance(e, MultiplyExpression)
    assert e.operator == MultiplyOperator.MULTIPLY


def test_mul_expr_divide() -> None:
    e = _evaluator("6 / 2")
    assert isinstance(e, MultiplyExpression)
    assert e.operator == MultiplyOperator.DIVIDE


def test_mul_expr_operands() -> None:
    e = _evaluator("2 * 3")
    assert isinstance(e, MultiplyExpression)
    assert isinstance(e.left_operand, Evaluator)
    assert isinstance(e.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.unary_expr
# ---------------------------------------------------------------------------


def test_unary_expr() -> None:
    e = _evaluator("-1")
    assert isinstance(e, UnaryExpression)
    assert e.operator == UnaryOperator.NEGATE
    assert isinstance(e.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.literal_expr
# ---------------------------------------------------------------------------


def test_literal_expr_number() -> None:
    e = _evaluator("42")
    assert isinstance(e, LiteralExpression)
    assert e.value == "42"


def test_literal_expr_string() -> None:
    e = _evaluator('"foo"')
    assert isinstance(e, LiteralExpression)
    assert e.value == "foo"


# ---------------------------------------------------------------------------
# OverpassTransformer.id_expr
# ---------------------------------------------------------------------------


def test_id_expr() -> None:
    e = _evaluator("id()")
    assert isinstance(e, MetadataExpression)
    assert e.attribute == MetadataAttribute.ID


# ---------------------------------------------------------------------------
# OverpassTransformer.type_expr
# ---------------------------------------------------------------------------


def test_type_expr() -> None:
    e = _evaluator("type()")
    assert isinstance(e, MetadataExpression)
    assert e.attribute == MetadataAttribute.TYPE


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_value_expr
# ---------------------------------------------------------------------------


def test_tag_value_expr() -> None:
    e = _evaluator('t["name"]')
    assert isinstance(e, TagValueExpression)
    assert isinstance(e.evaluator, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.is_tag_expr
# ---------------------------------------------------------------------------


def test_is_tag_expr() -> None:
    e = _evaluator("is_tag(name)")
    assert isinstance(e, IsTagExpression)
    assert isinstance(e.key, str)


# ---------------------------------------------------------------------------
# OverpassTransformer.keys_expr
# ---------------------------------------------------------------------------


def test_keys_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("keys()")


# ---------------------------------------------------------------------------
# OverpassTransformer.count_tags_expr
# ---------------------------------------------------------------------------


def test_count_tags_expr_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _evaluator("count_tags()")


# ---------------------------------------------------------------------------
# OverpassTransformer.count_members_expr
# ---------------------------------------------------------------------------


def test_count_members_expr_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _evaluator("count_members()")


# ---------------------------------------------------------------------------
# OverpassTransformer.count_distinct_members_expr
# ---------------------------------------------------------------------------


def test_count_distinct_members_expr_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _evaluator("count_distinct_members()")


# ---------------------------------------------------------------------------
# OverpassTransformer.count_by_role_expr
# ---------------------------------------------------------------------------


def test_count_by_role_expr_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _evaluator('count_by_role("outer")')


# ---------------------------------------------------------------------------
# OverpassTransformer.count_distinct_by_role_expr
# ---------------------------------------------------------------------------


def test_count_distinct_by_role_expr_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _evaluator('count_distinct_by_role("outer")')


# ---------------------------------------------------------------------------
# OverpassTransformer.is_closed_expr
# ---------------------------------------------------------------------------


def test_is_closed_expr() -> None:
    e = _evaluator("is_closed()")
    assert isinstance(e, IsClosedExpression)


# ---------------------------------------------------------------------------
# OverpassTransformer.lat_expr
# ---------------------------------------------------------------------------


def test_lat_expr() -> None:
    e = _evaluator("lat()")
    assert isinstance(e, CoordinateExpression)
    assert e.axis == CoordinateAxis.LAT


# ---------------------------------------------------------------------------
# OverpassTransformer.lon_expr
# ---------------------------------------------------------------------------


def test_lon_expr() -> None:
    e = _evaluator("lon()")
    assert isinstance(e, CoordinateExpression)
    assert e.axis == CoordinateAxis.LON


# ---------------------------------------------------------------------------
# OverpassTransformer.geom_expr
# ---------------------------------------------------------------------------


def test_geom_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("geom()")


# ---------------------------------------------------------------------------
# OverpassTransformer.length_expr
# ---------------------------------------------------------------------------


def test_length_expr() -> None:
    e = _evaluator("length()")
    assert isinstance(e, LengthExpression)


# ---------------------------------------------------------------------------
# OverpassTransformer.center_expr
# ---------------------------------------------------------------------------


def test_center_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("center(1)")


# ---------------------------------------------------------------------------
# OverpassTransformer.trace_expr
# ---------------------------------------------------------------------------


def test_trace_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("trace(1)")


# ---------------------------------------------------------------------------
# OverpassTransformer.hull_expr
# ---------------------------------------------------------------------------


def test_hull_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("hull(1)")


# ---------------------------------------------------------------------------
# OverpassTransformer.pt_expr
# ---------------------------------------------------------------------------


def test_pt_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("pt(1, 2)")


# ---------------------------------------------------------------------------
# OverpassTransformer.lstr_expr
# ---------------------------------------------------------------------------


def test_lstr_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("lstr(1, 2)")


# ---------------------------------------------------------------------------
# OverpassTransformer.poly_expr
# ---------------------------------------------------------------------------


def test_poly_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("poly(1, 2)")
