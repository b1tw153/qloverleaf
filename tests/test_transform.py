import dataclasses
from typing import Any

import pytest
from lark import Token, Tree

from qloverleaf.exceptions import (
    QueryError,
    UnimplementedFeatureError,
    UnsupportedFeatureError,
)
from qloverleaf.parser import parse
from qloverleaf.transform import (
    _NWR,
    _NWRA,
    AbsExpression,
    AddExpression,
    AddOperator,
    AreaIdFilter,
    AreaSetFilter,
    AroundLineFilter,
    BboxFilter,
    BinaryExpression,
    BinaryOperator,
    CompareExpression,
    CompareOperator,
    CompleteStatement,
    ConversionExpression,
    ConversionFunction,
    CoordinateAxis,
    CoordinateExpression,
    CountExpression,
    CountType,
    ElementType,
    Evaluator,
    ForeachStatement,
    ForStatement,
    IdFilter,
    IfFilter,
    IfStatement,
    IsClosedExpression,
    IsInStatement,
    IsTagExpression,
    ItemStatement,
    LengthExpression,
    LiteralExpression,
    MapToAreaStatement,
    MetadataAttribute,
    MetadataExpression,
    MultiplyExpression,
    MultiplyOperator,
    NewerFilter,
    OutSortOrder,
    OutStatement,
    OutVerbosity,
    OverpassTransformer,
    PivotFilter,
    PolygonFilter,
    QueryStatement,
    RecurseDir,
    RecurseFilter,
    RecurseFilterType,
    RecurseStatement,
    SetFilter,
    SetReference,
    SuffixExpression,
    TagFilterOp,
    TagKeyFilter,
    TagValueExpression,
    TagValueFilter,
    TernaryExpression,
    TypeCheckExpression,
    TypeCheckFunction,
    UidFilter,
    UnaryExpression,
    UnaryOperator,
    UnionStatement,
    UserFilter,
    ValExpression,
    WayCountFilter,
    _parse_datetime,
    _unquote,
)


def _transform_query(text: str) -> Any:
    return OverpassTransformer().transform(parse(text))


def _first_filter(text: str) -> Any:
    return _transform_query(text).children[0].children[0].filters[0]


def _assert_no_raw_nodes(value: Any, path: str = "root") -> None:
    """Recursively assert no Tree or Token appears outside .token fields."""
    if isinstance(value, (Tree, Token)):
        raise AssertionError(f"Raw Lark node at {path}: {type(value).__name__}")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            if field.name == "token":
                continue
            _assert_no_raw_nodes(getattr(value, field.name), f"{path}.{field.name}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _assert_no_raw_nodes(item, f"{path}[{i}]")
    elif isinstance(value, frozenset):
        for item in value:
            _assert_no_raw_nodes(item, f"{path}{{...}}")


def _stmt(text: str) -> Any:
    return _transform_query(text).children[0].children[0]


# ---------------------------------------------------------------------------
# IR completeness — no raw Tree/Token nodes outside .token fields
# ---------------------------------------------------------------------------


def test_ir_completeness_query_stmt() -> None:
    _assert_no_raw_nodes(
        _stmt('node[amenity=cafe][name~"Foo"](51.5,-0.2,51.6,-0.1)(123)(around:50.0);')
    )


def test_ir_completeness_filters() -> None:
    _assert_no_raw_nodes(_stmt('node(w.x)(r:"member")(area.y)(uid:1,2)(user:"alice");'))


# TODO: test_ir_completeness_foreach_stmt — body contains untransformed statement
# Trees until the query/statement rules are handled

# TODO: test_ir_completeness_for_stmt — same reason as foreach

# TODO: test_ir_completeness_complete_stmt — same reason as foreach

# TODO: test_ir_completeness_if_stmt — same reason as foreach

# TODO: test_ir_completeness_union_stmt — UnionMember.statement is an untransformed
# Tree until the query/statement rules are handled

# TODO: test_ir_completeness_val_expr — val_expr is only valid inside a for body;
# test via "for -> .a (1) { node(if:a.val); }" once block body transforms are handled


def test_ir_completeness_tag_and_positional_filters() -> None:
    _assert_no_raw_nodes(
        _stmt(
            'node[amenity][!name][amenity!=cafe][name!~"Foo"]'
            "(id:1,2,3)"
            "(around:100.0,51.5,-0.2)"
            "(around:100.0,51.5,-0.2,51.6,-0.1)"
            '(poly:"51.5 -0.2 51.6 -0.1 51.5 -0.3")'
            '(newer:"2024-03-12T11:03:25Z");'
        )
    )


def test_ir_completeness_remaining_filters() -> None:
    for query in [
        "node(area);",
        "node(area:3600000001);",
        "way(bn);",
        "rel(bw);",
        "rel(br);",
        "node(way_cnt:3);",
        "node.foo;",
        "way(pivot);",
        "node(if:1);",
        ".foo;",
    ]:
        _assert_no_raw_nodes(_stmt(query))


def test_ir_completeness_evaluators() -> None:
    for query in [
        # metadata
        "node(if:id());",
        "node(if:type());",
        "node(if:version());",
        "node(if:timestamp());",
        "node(if:changeset());",
        "node(if:uid());",
        "node(if:user());",
        # geometry
        "node(if:lat());",
        "node(if:lon());",
        "node(if:length());",
        "node(if:is_closed());",
        # tag access
        'node(if:t["name"]);',
        "node(if:is_tag(name));",
        # conversion and math
        "node(if:number(1));",
        "node(if:date(1));",
        "node(if:suffix(1));",
        "node(if:abs(-1));",
        "node(if:is_number(1));",
        "node(if:is_date(1));",
        # count
        "node(if:count(nodes));",
        # compound expressions
        "node(if:1 == 2);",
        "node(if:1 + 2);",
        "node(if:2 * 3);",
        "node(if:!1);",
        "node(if:1 ? 2 : 3);",
    ]:
        _assert_no_raw_nodes(_stmt(query))


def test_ir_completeness_out_stmt() -> None:
    _assert_no_raw_nodes(_stmt("out meta qt 10;"))


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
# OverpassTransformer.global_setting
# ---------------------------------------------------------------------------


def test_global_setting_timeout() -> None:
    _transform_query("[timeout:25];")


def test_global_setting_bbox() -> None:
    _transform_query("[bbox:51.5,-0.2,51.6,-0.1];")


def test_global_setting_out() -> None:
    _transform_query("[out:json];")


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_key
# ---------------------------------------------------------------------------


def test_tag_key_unquoted() -> None:
    filter = _first_filter("node[amenity];")
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "amenity"


def test_tag_key_quoted() -> None:
    filter = _first_filter('node["gnis:feature_id"];')
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "gnis:feature_id"


def test_tag_key_quoted_single() -> None:
    filter = _first_filter("node['gnis:feature_id'];")
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "gnis:feature_id"


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_key_regex
# ---------------------------------------------------------------------------

# tag_key_regex is a passthrough; tested via tag_filter_key_regex

# ---------------------------------------------------------------------------
# OverpassTransformer.tag_value
# ---------------------------------------------------------------------------


def test_tag_value_unquoted() -> None:
    filter = _first_filter("node[amenity=parking];")
    assert isinstance(filter, TagValueFilter)
    assert filter.value == "parking"


def test_tag_value_quoted() -> None:
    filter = _first_filter('node["addr:street"="Main Street"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.value == "Main Street"


def test_tag_value_quoted_single() -> None:
    filter = _first_filter("node['addr:street'='Main Street'];")
    assert isinstance(filter, TagValueFilter)
    assert filter.value == "Main Street"


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_value_regex / regex_case_insensitive
# ---------------------------------------------------------------------------


def test_tag_value_regex_simple() -> None:
    filter = _first_filter('node[amenity~"parking|parking_space"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.value == "parking|parking_space"


def test_tag_value_regex_simple_single_quoted() -> None:
    filter = _first_filter("node[amenity~'parking|parking_space'];")
    assert isinstance(filter, TagValueFilter)
    assert filter.value == "parking|parking_space"


def test_tag_value_regex_case_sensitive() -> None:
    filter = _first_filter('node[amenity~"parking|parking_space"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.case_insensitive is False


def test_tag_value_regex_case_insensitive() -> None:
    filter = _first_filter('node[amenity~"parking|parking_space",i];')
    assert isinstance(filter, TagValueFilter)
    assert filter.case_insensitive is True


# ---------------------------------------------------------------------------
# OverpassTransformer.around_radius
# ---------------------------------------------------------------------------

# around_radius returns a Token; tested via around_set_filter and around_point_filter

# ---------------------------------------------------------------------------
# OverpassTransformer.tag_filter_exists / tag_filter_absent
# ---------------------------------------------------------------------------


def test_tag_filter_exists() -> None:
    filter = _first_filter("node[amenity];")
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "amenity"
    assert filter.absent is False
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


def test_tag_filter_absent() -> None:
    filter = _first_filter("node[!amenity];")
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "amenity"
    assert filter.absent is True
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_filter_eq / tag_filter_neq
# ---------------------------------------------------------------------------


def test_tag_filter_eq() -> None:
    filter = _first_filter("node[amenity=cafe];")
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "amenity"
    assert filter.op == TagFilterOp.EQ
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


def test_tag_filter_neq() -> None:
    filter = _first_filter("node[amenity!=cafe];")
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "amenity"
    assert filter.op == TagFilterOp.NEQ
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_filter_regex / tag_filter_not_regex
# ---------------------------------------------------------------------------


def test_tag_filter_regex() -> None:
    filter = _first_filter('node[name~"cafe"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "name"
    assert filter.op == TagFilterOp.REGEX
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


def test_tag_filter_regex_case_insensitive() -> None:
    filter = _first_filter('node[name~"cafe",i];')
    assert isinstance(filter, TagValueFilter)
    assert filter.op == TagFilterOp.REGEX
    assert filter.case_insensitive is True
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


def test_tag_filter_not_regex() -> None:
    filter = _first_filter('node[name!~"cafe"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "name"
    assert filter.op == TagFilterOp.NOT_REGEX
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


def test_tag_filter_not_regex_case_insensitive() -> None:
    filter = _first_filter('node[name!~"cafe",i];')
    assert isinstance(filter, TagValueFilter)
    assert filter.op == TagFilterOp.NOT_REGEX
    assert filter.case_insensitive is True
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_filter_key_regex
# ---------------------------------------------------------------------------


def test_tag_filter_key_regex_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _first_filter('node[~"name"~"cafe"];')


# ---------------------------------------------------------------------------
# OverpassTransformer.bbox_filter
# ---------------------------------------------------------------------------


def test_bbox_filter_values() -> None:
    filter = _first_filter("node(51.5,-0.2,51.6,-0.1);")
    assert isinstance(filter, BboxFilter)
    assert filter.south == "51.5"
    assert filter.west == "-0.2"
    assert filter.north == "51.6"
    assert filter.east == "-0.1"
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


def test_bbox_filter_inverted_warns() -> None:
    transformer = OverpassTransformer()
    transformer.transform(parse("node(51.6,-0.2,51.5,-0.1);"))
    assert len(transformer.warnings) == 1
    assert "south >= north" in transformer.warnings[0].message


# ---------------------------------------------------------------------------
# OverpassTransformer.id_filter_single / id_filter_list
# ---------------------------------------------------------------------------


def test_id_filter_single() -> None:
    filter = _first_filter("node(123);")
    assert isinstance(filter, IdFilter)
    assert filter.ids == [123]
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


def test_id_filter_list() -> None:
    filter = _first_filter("node(id:1,2,3);")
    assert isinstance(filter, IdFilter)
    assert filter.ids == [1, 2, 3]
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.set_ref
# ---------------------------------------------------------------------------

# set_ref returns a SetReference; tested via recurse_filter

# ---------------------------------------------------------------------------
# OverpassTransformer.recurse_role
# ---------------------------------------------------------------------------

# recurse_role returns a str; tested via recurse_filter

# ---------------------------------------------------------------------------
# OverpassTransformer.int_range
# ---------------------------------------------------------------------------


def test_int_range_exact() -> None:
    filter = _first_filter("node(way_cnt:3);")
    assert filter.min_count == 3
    assert filter.max_count == 3
    assert filter.exact is True


def test_int_range_open_upper() -> None:
    filter = _first_filter("node(way_cnt:3-);")
    assert filter.min_count == 3
    assert filter.max_count is None
    assert filter.exact is False


def test_int_range_closed() -> None:
    filter = _first_filter("node(way_cnt:3-5);")
    assert filter.min_count == 3
    assert filter.max_count == 5
    assert filter.exact is False


# ---------------------------------------------------------------------------
# OverpassTransformer.set_name
# ---------------------------------------------------------------------------

# set_name returns a SetReference; tested in test_query_stmt_explicit_output_set

# ---------------------------------------------------------------------------
# OverpassTransformer.around_lat_lon (via around_point_filter)
# ---------------------------------------------------------------------------

# around_lat_lon returns a LatLon; tested in around_point_filter

# ---------------------------------------------------------------------------
# OverpassTransformer.around_line_filter
# ---------------------------------------------------------------------------


def test_around_line_filter() -> None:
    filter = _first_filter("node(around:100.0,51.5,-0.2,51.6,-0.1);")
    assert isinstance(filter, AroundLineFilter)
    assert filter.radius == "100.0"
    assert [(p.lat, p.lon) for p in filter.points] == [
        ("51.5", "-0.2"),
        ("51.6", "-0.1"),
    ]
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.poly_lat_lon (via polygon_filter)
# ---------------------------------------------------------------------------


def test_poly_lat_lon_values() -> None:
    filter = _first_filter('node(poly:"51.5 -0.2 51.6 -0.1 51.5 -0.3");')
    assert isinstance(filter, PolygonFilter)
    assert [(p.lat, p.lon) for p in filter.points] == [
        ("51.5", "-0.2"),
        ("51.6", "-0.1"),
        ("51.5", "-0.3"),
    ]
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.newer_filter
# ---------------------------------------------------------------------------


def test_newer_filter() -> None:
    filter = _first_filter('node(newer:"2024-03-12T11:03:25Z");')
    assert isinstance(filter, NewerFilter)
    assert filter.timestamp.year == 2024
    assert filter.timestamp.month == 3
    assert filter.timestamp.day == 12
    assert filter.token is not None
    assert filter.input_types == _NWR
    assert filter.output_types == _NWR


# ---------------------------------------------------------------------------
# OverpassTransformer.changed_filter
# ---------------------------------------------------------------------------


def test_changed_filter_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _first_filter('node(changed:"2024-03-12T11:03:25Z");')


# ---------------------------------------------------------------------------
# OverpassTransformer.user_filter
# ---------------------------------------------------------------------------


def test_user_filter_single() -> None:
    filter = _first_filter('node(user:"alice");')
    assert isinstance(filter, UserFilter)
    assert filter.users == ["alice"]
    assert filter.token is not None
    assert filter.input_types == _NWR
    assert filter.output_types == _NWR


def test_user_filter_multiple() -> None:
    filter = _first_filter('node(user:"alice","bob");')
    assert isinstance(filter, UserFilter)
    assert filter.users == ["alice", "bob"]
    assert filter.input_types == _NWR
    assert filter.output_types == _NWR


# ---------------------------------------------------------------------------
# OverpassTransformer.uid_filter
# ---------------------------------------------------------------------------


def test_uid_filter_single() -> None:
    filter = _first_filter("node(uid:42);")
    assert isinstance(filter, UidFilter)
    assert filter.uids == [42]
    assert filter.token is not None
    assert filter.input_types == _NWR
    assert filter.output_types == _NWR


def test_uid_filter_multiple() -> None:
    filter = _first_filter("node(uid:1,2,3);")
    assert isinstance(filter, UidFilter)
    assert filter.uids == [1, 2, 3]
    assert filter.input_types == _NWR
    assert filter.output_types == _NWR


# ---------------------------------------------------------------------------
# OverpassTransformer.user_touched_filter
# ---------------------------------------------------------------------------


def test_user_touched_filter_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _first_filter('node(user_touched:"alice");')


# ---------------------------------------------------------------------------
# OverpassTransformer.uid_touched_filter
# ---------------------------------------------------------------------------


def test_uid_touched_filter_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _first_filter("node(uid_touched:42);")


# ---------------------------------------------------------------------------
# OverpassTransformer.area_set_filter
# ---------------------------------------------------------------------------


def test_area_set_filter_default_set() -> None:
    filter = _first_filter("node(area);")
    assert isinstance(filter, AreaSetFilter)
    assert filter.set_ref.name == "_"
    assert filter.set_ref.token is None
    assert filter.set_ref.required_types == frozenset({ElementType.AREA})
    assert filter.token is None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


def test_area_set_filter_explicit_set() -> None:
    filter = _first_filter("node(area.foo);")
    assert isinstance(filter, AreaSetFilter)
    assert filter.set_ref.name == "foo"
    assert filter.set_ref.token is not None
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.area_id_filter
# ---------------------------------------------------------------------------


def test_area_id_filter() -> None:
    filter = _first_filter("node(area:3600000001);")
    assert isinstance(filter, AreaIdFilter)
    assert filter.area_id == 3600000001
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.recurse_filter
# ---------------------------------------------------------------------------


def test_recurse_filter_w() -> None:
    filter = _first_filter("node(w);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.W
    assert filter.input_types == frozenset({ElementType.NODE})
    assert filter.output_types == frozenset({ElementType.NODE})
    assert filter.set_ref.required_types == frozenset({ElementType.WAY})
    assert filter.set_ref.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_r() -> None:
    filter = _first_filter("node(r);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.R
    assert filter.input_types == frozenset(
        {ElementType.NODE, ElementType.WAY, ElementType.RELATION}
    )
    assert filter.output_types == frozenset(
        {ElementType.NODE, ElementType.WAY, ElementType.RELATION}
    )
    assert filter.set_ref.required_types == frozenset({ElementType.RELATION})
    assert filter.set_ref.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_bn() -> None:
    filter = _first_filter("way(bn);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.BN
    assert filter.input_types == frozenset({ElementType.WAY, ElementType.RELATION})
    assert filter.output_types == frozenset({ElementType.WAY, ElementType.RELATION})
    assert filter.set_ref.required_types == frozenset({ElementType.NODE})
    assert filter.set_ref.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_bw() -> None:
    filter = _first_filter("rel(bw);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.BW
    assert filter.input_types == frozenset({ElementType.RELATION})
    assert filter.output_types == frozenset({ElementType.RELATION})
    assert filter.set_ref.required_types == frozenset({ElementType.WAY})
    assert filter.set_ref.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_br() -> None:
    filter = _first_filter("rel(br);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.BR
    assert filter.input_types == frozenset({ElementType.RELATION})
    assert filter.output_types == frozenset({ElementType.RELATION})
    assert filter.set_ref.required_types == frozenset({ElementType.RELATION})
    assert filter.set_ref.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_explicit_set() -> None:
    filter = _first_filter("node(w.foo);")
    assert isinstance(filter, RecurseFilter)
    assert filter.set_ref.name == "foo"
    assert filter.set_ref.token is not None
    assert filter.set_ref.required_types == frozenset({ElementType.WAY})


def test_recurse_filter_role() -> None:
    filter = _first_filter('node(r:"member");')
    assert isinstance(filter, RecurseFilter)
    assert filter.role == "member"


# ---------------------------------------------------------------------------
# OverpassTransformer.way_count_filter
# ---------------------------------------------------------------------------


def test_way_count_filter() -> None:
    filter = _first_filter("node(way_cnt:3);")
    assert isinstance(filter, WayCountFilter)
    assert filter.set_ref.name == "_"
    assert filter.set_ref.token is None
    assert filter.set_ref.required_types == frozenset({ElementType.WAY})
    assert filter.min_count == 3
    assert filter.max_count == 3
    assert filter.exact is True
    assert filter.input_types == frozenset({ElementType.NODE})
    assert filter.output_types == frozenset({ElementType.NODE})
    assert filter.token is not None


def test_way_count_filter_named_set() -> None:
    filter = _first_filter("node(way_cnt.foo:3);")
    assert isinstance(filter, WayCountFilter)
    assert filter.set_ref.name == "foo"
    assert filter.set_ref.token is not None
    assert filter.set_ref.required_types == frozenset({ElementType.WAY})


# ---------------------------------------------------------------------------
# OverpassTransformer.way_link_filter
# ---------------------------------------------------------------------------


def test_way_link_filter_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _first_filter("node(way_link:2);")


# ---------------------------------------------------------------------------
# OverpassTransformer.set_filter
# ---------------------------------------------------------------------------


def test_set_filter() -> None:
    filter = _first_filter("node.foo;")
    assert isinstance(filter, SetFilter)
    assert filter.set_reference.name == "foo"
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types is None


# ---------------------------------------------------------------------------
# OverpassTransformer.pivot_filter
# ---------------------------------------------------------------------------


def test_pivot_filter_default_set() -> None:
    filter = _first_filter("way(pivot);")
    assert isinstance(filter, PivotFilter)
    assert filter.set_reference.name == "_"
    assert filter.set_reference.token is None
    assert filter.set_reference.required_types == frozenset({ElementType.AREA})
    assert filter.input_types == frozenset({ElementType.WAY, ElementType.RELATION})
    assert filter.output_types == frozenset({ElementType.WAY, ElementType.RELATION})
    assert filter.token is None


def test_pivot_filter_explicit_set() -> None:
    filter = _first_filter("way(pivot.foo);")
    assert isinstance(filter, PivotFilter)
    assert filter.set_reference.name == "foo"
    assert filter.set_reference.token is not None
    assert filter.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.if_filter
# ---------------------------------------------------------------------------


def test_if_filter() -> None:
    filter = _first_filter("node(if:1);")
    assert isinstance(filter, IfFilter)
    assert isinstance(filter.evaluator, Evaluator)
    assert filter.token is not None
    assert filter.input_types == _NWRA
    assert filter.output_types == _NWRA


# ---------------------------------------------------------------------------
# OverpassTransformer.set_assignment
# ---------------------------------------------------------------------------

# set_assignment is a passthrough; tested via query_stmt

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
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None
    assert stmt.output_set.required_types == frozenset({ElementType.NODE})


def test_query_stmt_way() -> None:
    stmt = _query_stmt("way;")
    assert stmt.element_types == frozenset({ElementType.WAY})
    assert stmt.output_set.required_types == frozenset({ElementType.WAY})


def test_query_stmt_relation() -> None:
    stmt = _query_stmt("relation;")
    assert stmt.element_types == frozenset({ElementType.RELATION})
    assert stmt.output_set.required_types == frozenset({ElementType.RELATION})


def test_query_stmt_nwr() -> None:
    stmt = _query_stmt("nwr;")
    assert stmt.element_types == frozenset(
        {ElementType.NODE, ElementType.WAY, ElementType.RELATION}
    )
    assert stmt.output_set.required_types == frozenset(
        {ElementType.NODE, ElementType.WAY, ElementType.RELATION}
    )


def test_query_stmt_nw() -> None:
    stmt = _query_stmt("nw;")
    assert stmt.element_types == frozenset({ElementType.NODE, ElementType.WAY})
    assert stmt.output_set.required_types == frozenset(
        {ElementType.NODE, ElementType.WAY}
    )


def test_query_stmt_wr() -> None:
    stmt = _query_stmt("wr;")
    assert stmt.element_types == frozenset({ElementType.WAY, ElementType.RELATION})
    assert stmt.output_set.required_types == frozenset(
        {ElementType.WAY, ElementType.RELATION}
    )


def test_query_stmt_nr() -> None:
    stmt = _query_stmt("nr;")
    assert stmt.element_types == frozenset({ElementType.NODE, ElementType.RELATION})
    assert stmt.output_set.required_types == frozenset(
        {ElementType.NODE, ElementType.RELATION}
    )


def test_query_stmt_area() -> None:
    stmt = _query_stmt("area;")
    assert stmt.element_types == frozenset({ElementType.AREA})
    assert stmt.output_set.required_types == frozenset({ElementType.AREA})


def test_query_stmt_filters() -> None:
    stmt = _query_stmt("node[amenity=cafe](51.5,-0.2,51.6,-0.1);")
    assert len(stmt.filters) == 2
    assert isinstance(stmt.filters[0], TagValueFilter)
    assert isinstance(stmt.filters[1], BboxFilter)


def test_query_stmt_output_set() -> None:
    stmt = _query_stmt("node[amenity=cafe] -> .x;")
    assert stmt.output_set.name == "x"
    assert stmt.output_set.required_types == frozenset({ElementType.NODE})


def test_query_stmt_no_output_set() -> None:
    stmt = _query_stmt("node[amenity=cafe];")
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None
    assert stmt.output_set.required_types == frozenset({ElementType.NODE})


# ---------------------------------------------------------------------------
# OverpassTransformer.block_body
# ---------------------------------------------------------------------------

# block_body is a passthrough; tested via foreach/for/complete body tests

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
    assert stmt.output_set.name == "y"


def test_foreach_no_output_set() -> None:
    stmt = _foreach_stmt("foreach .x { node; }")
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_foreach_output_set_without_input() -> None:
    stmt = _foreach_stmt("foreach -> .y { node; }")
    assert stmt.input_set.name == "_"
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
    assert stmt.output_set.name == "y"


def test_for_no_output_set() -> None:
    stmt = _for_stmt("for .x (1) { node; }")
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_for_output_set_without_input() -> None:
    stmt = _for_stmt("for -> .y (1) { node; }")
    assert stmt.input_set.name == "_"
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
    assert stmt.output_set.name == "y"


def test_complete_no_output_set() -> None:
    stmt = _complete_stmt("complete .x { node; }")
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_complete_output_set_without_input() -> None:
    stmt = _complete_stmt("complete -> .y { node; }")
    assert stmt.input_set.name == "_"
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
# OverpassTransformer.union_member
# ---------------------------------------------------------------------------

# union_member is a passthrough; tested via union_stmt

# ---------------------------------------------------------------------------
# OverpassTransformer.union_body
# ---------------------------------------------------------------------------

# union_body is a passthrough; tested via union_stmt

# ---------------------------------------------------------------------------
# OverpassTransformer.union_stmt
# ---------------------------------------------------------------------------


def _union_stmt(text: str) -> UnionStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, UnionStatement)
    return stmt


def test_union_members() -> None:
    stmt = _union_stmt("( node(1); node(2); node(3); );")
    assert len(stmt.members) == 3


def test_union_member_difference() -> None:
    stmt = _union_stmt("( node(1); node(2); - node(3); );")
    assert stmt.members[0].difference is False
    assert stmt.members[1].difference is False
    assert stmt.members[2].difference is True


# TODO: test_union_member_statement — once statement production is handled


def test_union_output_set() -> None:
    stmt = _union_stmt("( node(1); node(2); ) -> .x;")
    assert stmt.output_set.name == "x"
    assert stmt.output_set.token is not None


def test_union_no_output_set() -> None:
    stmt = _union_stmt("( node(1); node(2); );")
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


# TODO: test_union_token — token comes from first member's statement
# revisit once statement production is handled


def test_union_empty() -> None:
    stmt = _union_stmt("();")
    assert len(stmt.members) == 0
    assert stmt.token is None


def test_union_empty_token_with_output_set() -> None:
    stmt = _union_stmt("() -> .x;")
    assert len(stmt.members) == 0
    assert stmt.output_set.name == "x"
    assert stmt.output_set.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.item_stmt
# ---------------------------------------------------------------------------


def _item_stmt(text: str) -> ItemStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, ItemStatement)
    return stmt


def test_item_input_set() -> None:
    stmt = _item_stmt(".foo;")
    assert stmt.input_set.name == "foo"
    assert isinstance(stmt.input_set.token, Token)


def test_item_no_output_set() -> None:
    stmt = _item_stmt(".foo;")
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_item_output_set() -> None:
    stmt = _item_stmt(".foo -> .bar;")
    assert stmt.output_set.name == "bar"


def test_item_token() -> None:
    stmt = _item_stmt(".foo;")
    assert isinstance(stmt.token, Token)


# ---------------------------------------------------------------------------
# OverpassTransformer.out_token
# ---------------------------------------------------------------------------

# out_token is a passthrough; tested via out_stmt

# ---------------------------------------------------------------------------
# OverpassTransformer.out_stmt
# ---------------------------------------------------------------------------


def _out_stmt(text: str) -> OutStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, OutStatement)
    return stmt


def test_out_default() -> None:
    stmt = _out_stmt("out;")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None
    assert stmt.count is False
    assert stmt.verbosity == OutVerbosity.BODY
    assert stmt.geom is False
    assert stmt.bb is False
    assert stmt.center is False
    assert stmt.sort_order == OutSortOrder.ASC
    assert stmt.limit is None
    assert stmt.token is None


def test_out_input_set() -> None:
    stmt = _out_stmt(".foo out;")
    assert stmt.input_set.name == "foo"
    assert isinstance(stmt.input_set.token, Token)


def test_out_verbosity_ids() -> None:
    stmt = _out_stmt("out ids;")
    assert stmt.verbosity == OutVerbosity.IDS


def test_out_verbosity_skel() -> None:
    stmt = _out_stmt("out skel;")
    assert stmt.verbosity == OutVerbosity.SKEL


def test_out_verbosity_tags() -> None:
    stmt = _out_stmt("out tags;")
    assert stmt.verbosity == OutVerbosity.TAGS


def test_out_verbosity_body() -> None:
    stmt = _out_stmt("out body;")
    assert stmt.verbosity == OutVerbosity.BODY


def test_out_verbosity_meta() -> None:
    stmt = _out_stmt("out meta;")
    assert stmt.verbosity == OutVerbosity.META


def test_out_count() -> None:
    stmt = _out_stmt("out count;")
    assert stmt.count is True
    assert stmt.verbosity == OutVerbosity.BODY


def test_out_geom() -> None:
    stmt = _out_stmt("out geom;")
    assert stmt.geom is True
    assert stmt.bb is False
    assert stmt.center is False


def test_out_bb() -> None:
    stmt = _out_stmt("out bb;")
    assert stmt.bb is True
    assert stmt.geom is False
    assert stmt.center is False


def test_out_center() -> None:
    stmt = _out_stmt("out center;")
    assert stmt.center is True
    assert stmt.geom is False
    assert stmt.bb is False


def test_out_geom_center() -> None:
    stmt = _out_stmt("out geom center;")
    assert stmt.geom is True
    assert stmt.center is True
    assert stmt.bb is False


def test_out_bb_center() -> None:
    stmt = _out_stmt("out bb center;")
    assert stmt.bb is True
    assert stmt.center is True
    assert stmt.geom is False


def test_out_sort_qt() -> None:
    stmt = _out_stmt("out qt;")
    assert stmt.sort_order == OutSortOrder.QT


def test_out_sort_asc() -> None:
    stmt = _out_stmt("out asc;")
    assert stmt.sort_order == OutSortOrder.ASC


def test_out_limit() -> None:
    stmt = _out_stmt("out 10;")
    assert stmt.limit == 10


def test_out_verbosity_and_geometry() -> None:
    stmt = _out_stmt("out ids geom;")
    assert stmt.verbosity == OutVerbosity.IDS
    assert stmt.geom is True


def test_out_verbosity_and_sort() -> None:
    stmt = _out_stmt("out meta qt;")
    assert stmt.verbosity == OutVerbosity.META
    assert stmt.sort_order == OutSortOrder.QT


def test_out_verbosity_and_limit() -> None:
    stmt = _out_stmt("out skel 5;")
    assert stmt.verbosity == OutVerbosity.SKEL
    assert stmt.limit == 5


def test_out_token_from_verb() -> None:
    stmt = _out_stmt("out ids;")
    assert isinstance(stmt.token, Token)


def test_out_duplicate_verb_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out body body;")


def test_out_duplicate_verbosity_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out ids body;")


def test_out_geom_and_bb_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out geom bb;")


def test_out_duplicate_sort_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out asc qt;")


def test_out_duplicate_limit_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out 5 10;")


def test_out_count_with_verbosity_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out count body;")


def test_out_count_with_geom_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out count geom;")


def test_out_count_with_bb_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out count bb;")


def test_out_count_with_center_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out count center;")


def test_out_count_with_sort_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out count qt;")


def test_out_count_with_limit_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out count 5;")


def test_out_noids_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _out_stmt("out noids;")


def test_out_bbox_filter_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _out_stmt("out geom (1,2,3,4);")


# ---------------------------------------------------------------------------
# OverpassTransformer.recurse_stmt
# ---------------------------------------------------------------------------


def _recurse_stmt(text: str) -> RecurseStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, RecurseStatement)
    return stmt


def test_recurse_default_sets() -> None:
    stmt = _recurse_stmt(">;")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_recurse_dir_down() -> None:
    stmt = _recurse_stmt(">;")
    assert stmt.recurse_dir == RecurseDir.DOWN


def test_recurse_dir_up() -> None:
    stmt = _recurse_stmt("<;")
    assert stmt.recurse_dir == RecurseDir.UP


def test_recurse_dir_down_relations() -> None:
    stmt = _recurse_stmt(">>;")
    assert stmt.recurse_dir == RecurseDir.DOWN_RELATIONS


def test_recurse_dir_up_relations() -> None:
    stmt = _recurse_stmt("<<;")
    assert stmt.recurse_dir == RecurseDir.UP_RELATIONS


def test_recurse_input_set() -> None:
    stmt = _recurse_stmt(".foo >;")
    assert stmt.input_set.name == "foo"
    assert isinstance(stmt.input_set.token, Token)


def test_recurse_output_set() -> None:
    stmt = _recurse_stmt("> -> .bar;")
    assert stmt.output_set.name == "bar"


def test_recurse_token_from_dir() -> None:
    stmt = _recurse_stmt(">;")
    assert isinstance(stmt.token, Token)


def test_recurse_token_from_input_set() -> None:
    stmt = _recurse_stmt(".foo >;")
    assert isinstance(stmt.token, Token)
    assert stmt.token.value == "foo"


# ---------------------------------------------------------------------------
# OverpassTransformer.is_in_stmt
# ---------------------------------------------------------------------------


def _is_in_stmt(text: str) -> IsInStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, IsInStatement)
    return stmt


def test_is_in_default() -> None:
    stmt = _is_in_stmt("is_in;")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None
    assert stmt.lat is None
    assert stmt.lon is None
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None
    assert stmt.token is None


def test_is_in_input_set() -> None:
    stmt = _is_in_stmt(".foo is_in;")
    assert stmt.input_set.name == "foo"
    assert isinstance(stmt.input_set.token, Token)
    assert isinstance(stmt.token, Token)
    assert stmt.token.value == "foo"


def test_is_in_coordinates() -> None:
    stmt = _is_in_stmt("is_in(51.5,-0.2);")
    assert stmt.lat == "51.5"
    assert stmt.lon == "-0.2"
    assert isinstance(stmt.token, Token)


def test_is_in_output_set() -> None:
    stmt = _is_in_stmt("is_in -> .bar;")
    assert stmt.output_set.name == "bar"
    assert isinstance(stmt.token, Token)
    assert stmt.token.value == "bar"


# ---------------------------------------------------------------------------
# OverpassTransformer.timeline_stmt
# ---------------------------------------------------------------------------


def test_timeline_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _transform_query("timeline(node,1);")


# ---------------------------------------------------------------------------
# OverpassTransformer.local_stmt
# ---------------------------------------------------------------------------


def test_local_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _transform_query("local;")


# ---------------------------------------------------------------------------
# OverpassTransformer.convert_stmt
# ---------------------------------------------------------------------------


def test_convert_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _transform_query("convert mytype;")


# ---------------------------------------------------------------------------
# OverpassTransformer.make_stmt
# ---------------------------------------------------------------------------


def test_make_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _transform_query("make mytype;")


# ---------------------------------------------------------------------------
# OverpassTransformer.map_to_area_stmt
# ---------------------------------------------------------------------------


def _map_to_area_stmt(text: str) -> MapToAreaStatement:
    stmt = _transform_query(text).children[0].children[0]
    assert isinstance(stmt, MapToAreaStatement)
    return stmt


def test_map_to_area_default() -> None:
    stmt = _map_to_area_stmt("map_to_area;")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None
    assert stmt.input_set.required_types == frozenset(
        {ElementType.WAY, ElementType.RELATION}
    )
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None
    assert stmt.output_set.required_types == frozenset({ElementType.AREA})
    assert stmt.token is None


def test_map_to_area_input_set() -> None:
    stmt = _map_to_area_stmt(".foo map_to_area;")
    assert stmt.input_set.name == "foo"
    assert stmt.input_set.required_types == frozenset(
        {ElementType.WAY, ElementType.RELATION}
    )
    assert isinstance(stmt.input_set.token, Token)
    assert isinstance(stmt.token, Token)
    assert stmt.token.value == "foo"


def test_map_to_area_output_set() -> None:
    stmt = _map_to_area_stmt("map_to_area -> .bar;")
    assert stmt.output_set.name == "bar"
    assert stmt.output_set.required_types == frozenset({ElementType.AREA})
    assert isinstance(stmt.token, Token)
    assert stmt.token.value == "bar"


# ---------------------------------------------------------------------------
# OverpassTransformer.compare_stmt
# ---------------------------------------------------------------------------


def test_compare_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _transform_query("compare();")


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
    expr = _evaluator("1 ? 2 : 3")
    assert isinstance(expr, TernaryExpression)
    assert isinstance(expr.condition, Evaluator)
    assert isinstance(expr.true_expression, Evaluator)
    assert isinstance(expr.false_expression, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.or_expr
# ---------------------------------------------------------------------------


def test_or_expr() -> None:
    expr = _evaluator("1 || 0")
    assert isinstance(expr, BinaryExpression)
    assert expr.operator == BinaryOperator.OR
    assert len(expr.operands) == 2


def test_or_expr_repeated() -> None:
    expr = _evaluator("1 || 0 || 1")
    assert isinstance(expr, BinaryExpression)
    assert expr.operator == BinaryOperator.OR
    assert len(expr.operands) == 3


# ---------------------------------------------------------------------------
# OverpassTransformer.and_expr
# ---------------------------------------------------------------------------


def test_and_expr() -> None:
    expr = _evaluator("1 && 0")
    assert isinstance(expr, BinaryExpression)
    assert expr.operator == BinaryOperator.AND
    assert len(expr.operands) == 2


def test_and_expr_repeated() -> None:
    expr = _evaluator("1 && 0 && 1")
    assert isinstance(expr, BinaryExpression)
    assert expr.operator == BinaryOperator.AND
    assert len(expr.operands) == 3


# ---------------------------------------------------------------------------
# OverpassTransformer.not_expr
# ---------------------------------------------------------------------------


def test_not_expr() -> None:
    expr = _evaluator("!1")
    assert isinstance(expr, UnaryExpression)
    assert expr.operator == UnaryOperator.NOT
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.compare_expr
# ---------------------------------------------------------------------------


def test_compare_expr_equal() -> None:
    expr = _evaluator("1 == 2")
    assert isinstance(expr, CompareExpression)
    assert expr.operator == CompareOperator.EQUAL


def test_compare_expr_not_equal() -> None:
    expr = _evaluator("1 != 2")
    assert isinstance(expr, CompareExpression)
    assert expr.operator == CompareOperator.NOT_EQUAL


def test_compare_expr_less_than() -> None:
    expr = _evaluator("1 < 2")
    assert isinstance(expr, CompareExpression)
    assert expr.operator == CompareOperator.LESS_THAN


def test_compare_expr_greater_than() -> None:
    expr = _evaluator("1 > 2")
    assert isinstance(expr, CompareExpression)
    assert expr.operator == CompareOperator.GREATER_THAN


def test_compare_expr_less_than_or_equal() -> None:
    expr = _evaluator("1 <= 2")
    assert isinstance(expr, CompareExpression)
    assert expr.operator == CompareOperator.LESS_THAN_OR_EQUAL


def test_compare_expr_greater_than_or_equal() -> None:
    expr = _evaluator("1 >= 2")
    assert isinstance(expr, CompareExpression)
    assert expr.operator == CompareOperator.GREATER_THAN_OR_EQUAL


def test_compare_expr_operands() -> None:
    expr = _evaluator("1 == 2")
    assert isinstance(expr, CompareExpression)
    assert isinstance(expr.left_operand, Evaluator)
    assert isinstance(expr.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.add_expr
# ---------------------------------------------------------------------------


def test_add_expr_add() -> None:
    expr = _evaluator("1 + 2")
    assert isinstance(expr, AddExpression)
    assert expr.operator == AddOperator.ADD


def test_add_expr_subtract() -> None:
    expr = _evaluator("1 - 2")
    assert isinstance(expr, AddExpression)
    assert expr.operator == AddOperator.SUBTRACT


def test_add_expr_operands() -> None:
    expr = _evaluator("1 + 2")
    assert isinstance(expr, AddExpression)
    assert isinstance(expr.left_operand, Evaluator)
    assert isinstance(expr.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.mul_expr
# ---------------------------------------------------------------------------


def test_mul_expr_multiply() -> None:
    expr = _evaluator("2 * 3")
    assert isinstance(expr, MultiplyExpression)
    assert expr.operator == MultiplyOperator.MULTIPLY


def test_mul_expr_divide() -> None:
    expr = _evaluator("6 / 2")
    assert isinstance(expr, MultiplyExpression)
    assert expr.operator == MultiplyOperator.DIVIDE


def test_mul_expr_operands() -> None:
    expr = _evaluator("2 * 3")
    assert isinstance(expr, MultiplyExpression)
    assert isinstance(expr.left_operand, Evaluator)
    assert isinstance(expr.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.unary_expr
# ---------------------------------------------------------------------------


def test_unary_expr() -> None:
    expr = _evaluator("-1")
    assert isinstance(expr, UnaryExpression)
    assert expr.operator == UnaryOperator.NEGATE
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.literal_expr
# ---------------------------------------------------------------------------


def test_literal_expr_number() -> None:
    expr = _evaluator("42")
    assert isinstance(expr, LiteralExpression)
    assert expr.value == "42"


def test_literal_expr_string() -> None:
    expr = _evaluator('"foo"')
    assert isinstance(expr, LiteralExpression)
    assert expr.value == "foo"


# ---------------------------------------------------------------------------
# OverpassTransformer.id_expr
# ---------------------------------------------------------------------------


def test_id_expr() -> None:
    expr = _evaluator("id()")
    assert isinstance(expr, MetadataExpression)
    assert expr.attribute == MetadataAttribute.ID


# ---------------------------------------------------------------------------
# OverpassTransformer.type_expr
# ---------------------------------------------------------------------------


def test_type_expr() -> None:
    expr = _evaluator("type()")
    assert isinstance(expr, MetadataExpression)
    assert expr.attribute == MetadataAttribute.TYPE


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_value_expr
# ---------------------------------------------------------------------------


def test_tag_value_expr() -> None:
    expr = _evaluator('t["name"]')
    assert isinstance(expr, TagValueExpression)
    assert isinstance(expr.evaluator, LiteralExpression)


def test_tag_value_expr_dynamic_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('t["prefix" + "suffix"]')


# ---------------------------------------------------------------------------
# OverpassTransformer.is_tag_expr
# ---------------------------------------------------------------------------


def test_is_tag_expr() -> None:
    expr = _evaluator("is_tag(name)")
    assert isinstance(expr, IsTagExpression)
    assert isinstance(expr.key, str)


# ---------------------------------------------------------------------------
# OverpassTransformer.keys_expr
# ---------------------------------------------------------------------------


def test_keys_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("keys()")


# ---------------------------------------------------------------------------
# OverpassTransformer.version_expr
# ---------------------------------------------------------------------------


def test_version_expr() -> None:
    expr = _evaluator("version()")
    assert isinstance(expr, MetadataExpression)
    assert expr.attribute == MetadataAttribute.VERSION
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.timestamp_expr
# ---------------------------------------------------------------------------


def test_timestamp_expr() -> None:
    expr = _evaluator("timestamp()")
    assert isinstance(expr, MetadataExpression)
    assert expr.attribute == MetadataAttribute.TIMESTAMP
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.changeset_expr
# ---------------------------------------------------------------------------


def test_changeset_expr() -> None:
    expr = _evaluator("changeset()")
    assert isinstance(expr, MetadataExpression)
    assert expr.attribute == MetadataAttribute.CHANGESET
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.uid_expr
# ---------------------------------------------------------------------------


def test_uid_expr() -> None:
    expr = _evaluator("uid()")
    assert isinstance(expr, MetadataExpression)
    assert expr.attribute == MetadataAttribute.UID
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.user_expr
# ---------------------------------------------------------------------------


def test_user_expr() -> None:
    expr = _evaluator("user()")
    assert isinstance(expr, MetadataExpression)
    assert expr.attribute == MetadataAttribute.USER
    assert expr.token is not None


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
    expr = _evaluator("is_closed()")
    assert isinstance(expr, IsClosedExpression)


# ---------------------------------------------------------------------------
# OverpassTransformer.lat_expr
# ---------------------------------------------------------------------------


def test_lat_expr() -> None:
    expr = _evaluator("lat()")
    assert isinstance(expr, CoordinateExpression)
    assert expr.axis == CoordinateAxis.LAT


# ---------------------------------------------------------------------------
# OverpassTransformer.lon_expr
# ---------------------------------------------------------------------------


def test_lon_expr() -> None:
    expr = _evaluator("lon()")
    assert isinstance(expr, CoordinateExpression)
    assert expr.axis == CoordinateAxis.LON


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
    expr = _evaluator("length()")
    assert isinstance(expr, LengthExpression)


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


# ---------------------------------------------------------------------------
# OverpassTransformer.per_member_expr
# ---------------------------------------------------------------------------


def test_per_member_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("per_member(1)")


# ---------------------------------------------------------------------------
# OverpassTransformer.per_vertex_expr
# ---------------------------------------------------------------------------


def test_per_vertex_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("per_vertex(1)")


# ---------------------------------------------------------------------------
# OverpassTransformer.pos_expr
# ---------------------------------------------------------------------------


def test_pos_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("pos()")


# ---------------------------------------------------------------------------
# OverpassTransformer.mtype_expr
# ---------------------------------------------------------------------------


def test_mtype_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("mtype()")


# ---------------------------------------------------------------------------
# OverpassTransformer.ref_expr
# ---------------------------------------------------------------------------


def test_ref_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("ref()")


# ---------------------------------------------------------------------------
# OverpassTransformer.role_expr
# ---------------------------------------------------------------------------


def test_role_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("role()")


# ---------------------------------------------------------------------------
# OverpassTransformer.angle_expr
# ---------------------------------------------------------------------------


def test_angle_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("angle()")


# ---------------------------------------------------------------------------
# OverpassTransformer.unique_expr
# ---------------------------------------------------------------------------


def test_unique_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('u(t["name"])')


def test_unique_expr_with_set_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('a.u(t["name"])')


# ---------------------------------------------------------------------------
# OverpassTransformer.min_expr
# ---------------------------------------------------------------------------


def test_min_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('min(t["ele"])')


def test_min_expr_with_set_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('a.min(t["ele"])')


# ---------------------------------------------------------------------------
# OverpassTransformer.max_expr
# ---------------------------------------------------------------------------


def test_max_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('max(t["ele"])')


def test_max_expr_with_set_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('a.max(t["ele"])')


# ---------------------------------------------------------------------------
# OverpassTransformer.sum_expr
# ---------------------------------------------------------------------------


def test_sum_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('sum(t["ele"])')


def test_sum_expr_with_set_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('a.sum(t["ele"])')


# ---------------------------------------------------------------------------
# OverpassTransformer.set_expr
# ---------------------------------------------------------------------------


def test_set_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('set(t["name"])')


def test_set_expr_with_set_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('a.set(t["name"])')


# ---------------------------------------------------------------------------
# OverpassTransformer.gcat_expr
# ---------------------------------------------------------------------------


def test_gcat_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("gcat(geom())")


def test_gcat_expr_with_set_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("a.gcat(geom())")


# ---------------------------------------------------------------------------
# OverpassTransformer.count_expr
# ---------------------------------------------------------------------------


def test_count_nodes() -> None:
    expr = _evaluator("count(nodes)")
    assert isinstance(expr, CountExpression)
    assert expr.count_type == CountType.NODES
    assert expr.set_ref.name == "_"
    assert expr.set_ref.token is None


def test_count_ways() -> None:
    expr = _evaluator("count(ways)")
    assert isinstance(expr, CountExpression)
    assert expr.count_type == CountType.WAYS
    assert expr.set_ref.name == "_"
    assert expr.set_ref.token is None


def test_count_relations() -> None:
    expr = _evaluator("count(relations)")
    assert isinstance(expr, CountExpression)
    assert expr.count_type == CountType.RELATIONS
    assert expr.set_ref.name == "_"
    assert expr.set_ref.token is None


def test_count_nw() -> None:
    expr = _evaluator("count(nw)")
    assert isinstance(expr, CountExpression)
    assert expr.count_type == CountType.NW


def test_count_wr() -> None:
    expr = _evaluator("count(wr)")
    assert isinstance(expr, CountExpression)
    assert expr.count_type == CountType.WR


def test_count_nr() -> None:
    expr = _evaluator("count(nr)")
    assert isinstance(expr, CountExpression)
    assert expr.count_type == CountType.NR


def test_count_nwr() -> None:
    expr = _evaluator("count(nwr)")
    assert isinstance(expr, CountExpression)
    assert expr.count_type == CountType.NWR


def test_count_with_set() -> None:
    expr = _evaluator("a.count(nodes)")
    assert isinstance(expr, CountExpression)
    assert expr.count_type == CountType.NODES
    assert isinstance(expr.set_ref, SetReference)
    assert expr.set_ref.name == "a"


def test_count_deriveds_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("count(deriveds)")


def test_count_deriveds_with_set_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("a.count(deriveds)")


# ---------------------------------------------------------------------------
# OverpassTransformer.lrs_in_expr
# ---------------------------------------------------------------------------


def test_lrs_in_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("lrs_in(1, 2)")


# ---------------------------------------------------------------------------
# OverpassTransformer.lrs_isect_expr
# ---------------------------------------------------------------------------


def test_lrs_isect_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("lrs_isect(1, 2)")


# ---------------------------------------------------------------------------
# OverpassTransformer.lrs_union_expr
# ---------------------------------------------------------------------------


def test_lrs_union_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("lrs_union(1, 2)")


# ---------------------------------------------------------------------------
# OverpassTransformer.lrs_min_expr
# ---------------------------------------------------------------------------


def test_lrs_min_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("lrs_min(1)")


# ---------------------------------------------------------------------------
# OverpassTransformer.lrs_max_expr
# ---------------------------------------------------------------------------


def test_lrs_max_expr_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator("lrs_max(1)")


# ---------------------------------------------------------------------------
# OverpassTransformer.val_expr
# ---------------------------------------------------------------------------


def test_val_expr() -> None:
    result = _evaluator("a.val")
    assert isinstance(result, ValExpression)
    assert result.set_ref.name == "a"
    assert isinstance(result.set_ref.token, Token)


# ---------------------------------------------------------------------------
# OverpassTransformer.number_expr
# ---------------------------------------------------------------------------


def test_number_expr() -> None:
    expr = _evaluator('number(t["ele"])')
    assert isinstance(expr, ConversionExpression)
    assert expr.function == ConversionFunction.NUMBER
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.date_expr
# ---------------------------------------------------------------------------


def test_date_expr() -> None:
    expr = _evaluator('date(t["start_date"])')
    assert isinstance(expr, ConversionExpression)
    assert expr.function == ConversionFunction.DATE


# ---------------------------------------------------------------------------
# OverpassTransformer.suffix_expr
# ---------------------------------------------------------------------------


def test_suffix_expr() -> None:
    expr = _evaluator('suffix(t["ele"])')
    assert isinstance(expr, SuffixExpression)
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.abs_expr
# ---------------------------------------------------------------------------


def test_abs_expr() -> None:
    expr = _evaluator("abs(-1)")
    assert isinstance(expr, AbsExpression)
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.is_number_expr
# ---------------------------------------------------------------------------


def test_is_number_expr() -> None:
    expr = _evaluator('is_number(t["ele"])')
    assert isinstance(expr, TypeCheckExpression)
    assert expr.function == TypeCheckFunction.IS_NUMBER
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.is_date_expr
# ---------------------------------------------------------------------------


def test_is_date_expr() -> None:
    expr = _evaluator('is_date(t["start_date"])')
    assert isinstance(expr, TypeCheckExpression)
    assert expr.function == TypeCheckFunction.IS_DATE
