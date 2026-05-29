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
from qloverleaf.transformer import (
    _AREA,
    _NODE,
    _NONE,
    _NWR,
    _RELATION,
    _WAY,
    _WR,
    AbsEvaluator,
    AddEvaluator,
    AddOperator,
    AggregateOperator,
    AreaIdFilter,
    AreaSetFilter,
    AroundLineFilter,
    AroundSetFilter,
    BboxFilter,
    BinaryEvaluator,
    BinaryOperator,
    CompareEvaluator,
    CompareOperator,
    CompleteStatement,
    ConversionEvaluator,
    ConversionFunction,
    CoordinateAxis,
    CoordinateEvaluator,
    CountByRoleEvaluator,
    CountEvaluator,
    CountMembersEvaluator,
    CountTagsEvaluator,
    CountType,
    ElementType,
    Evaluator,
    ForeachStatement,
    ForStatement,
    IdFilter,
    IfFilter,
    IfStatement,
    IsClosedEvaluator,
    IsInStatement,
    IsTagEvaluator,
    ItemStatement,
    LengthEvaluator,
    LiteralEvaluator,
    MapToAreaStatement,
    MetadataAttribute,
    MetadataEvaluator,
    MinMaxEvaluator,
    MultiplyEvaluator,
    MultiplyOperator,
    NewerFilter,
    OutSortOrder,
    OutStatement,
    OutVerbosity,
    OverpassTransformer,
    PivotFilter,
    PolygonFilter,
    Query,
    QueryStatement,
    RecurseDir,
    RecurseFilter,
    RecurseFilterType,
    RecurseStatement,
    SetFilter,
    SetReference,
    Statement,
    SuffixEvaluator,
    SumEvaluator,
    TagFilterOp,
    TagKeyFilter,
    TagValueEvaluator,
    TagValueFilter,
    TernaryEvaluator,
    TypeCheckEvaluator,
    TypeCheckFunction,
    UidFilter,
    UnaryEvaluator,
    UnaryOperator,
    UnionStatement,
    UniqueEvaluator,
    UserFilter,
    ValEvaluator,
    Warning,
    WayCountFilter,
    _parse_datetime,
    _unquote,
)


def _transform_query(text: str) -> Any:
    return OverpassTransformer().transform(parse(text))


def _first_filter(text: str) -> Any:
    return _transform_query(text).statements[0].filters[0]


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
    return _transform_query(text).statements[0]


# ---------------------------------------------------------------------------
# IR completeness — no raw Tree/Token nodes outside .token fields
# ---------------------------------------------------------------------------


def test_ir_completeness_query_stmt() -> None:
    _assert_no_raw_nodes(
        _stmt('node[amenity=cafe][name~"Foo"](51.5,-0.2,51.6,-0.1)(123)(around:50.0);')
    )


def test_ir_completeness_filters() -> None:
    _assert_no_raw_nodes(_stmt('node(w.x)(r:"member")(area.y)(uid:1,2)(user:"alice");'))


def test_ir_completeness_foreach_stmt() -> None:
    _assert_no_raw_nodes(_stmt("foreach .x { node[amenity=cafe]; }"))


def test_ir_completeness_for_stmt() -> None:
    _assert_no_raw_nodes(_stmt("for -> .a (1) { node[amenity=cafe]; }"))


def test_ir_completeness_complete_stmt() -> None:
    _assert_no_raw_nodes(_stmt("complete { node[amenity=cafe]; }"))


def test_ir_completeness_if_stmt() -> None:
    _assert_no_raw_nodes(
        _stmt("if (1) { node[amenity=cafe]; } else { node[amenity=parking]; }")
    )


def test_ir_completeness_union_stmt() -> None:
    _assert_no_raw_nodes(_stmt("( node(1); way(1); );"))


def test_ir_completeness_val_expr() -> None:
    _assert_no_raw_nodes(_stmt("for -> .a (1) { node(if:a.val); }"))


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
    _assert_no_raw_nodes(_stmt("out meta asc 10;"))


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
# OverpassTransformer.query
# ---------------------------------------------------------------------------


def test_query_settings_only() -> None:
    result = _transform_query("[out:json];")
    assert isinstance(result, Query)
    assert result.statements == []
    assert result.warnings == []


def test_query_single_statement() -> None:
    result = _transform_query("node;")
    assert isinstance(result, Query)
    assert len(result.statements) == 1
    assert isinstance(result.statements[0], QueryStatement)


def test_query_multiple_statements() -> None:
    result = _transform_query("node;way;relation;")
    assert isinstance(result, Query)
    assert len(result.statements) == 3


def test_query_settings_block_statements() -> None:
    result = _transform_query("if(1){node;}else{way;}foreach->.a{.a out;}")
    assert isinstance(result, Query)
    assert len(result.statements) == 2


def test_query_settings_excluded_from_statements() -> None:
    result = _transform_query("[out:json][timeout:25];node;")
    assert isinstance(result, Query)
    assert len(result.statements) == 1


# ---------------------------------------------------------------------------
# _resolve_types (Phase 2 — Set Version Assignment)
# ---------------------------------------------------------------------------


def test_resolve_types_write() -> None:
    stmt = _transform_query("node;").statements[0]
    assert isinstance(stmt, QueryStatement)
    assert stmt.output_set.version == 1
    assert stmt.output_set.content_types == _NODE


def test_resolve_types_sequential_writes() -> None:
    stmts = _transform_query("node;way;").statements
    assert stmts[0].output_set.version == 1
    assert stmts[1].output_set.version == 2


def test_resolve_types_named_set_independent_version() -> None:
    stmts = _transform_query("node -> .a; way;").statements
    assert stmts[0].output_set.version == 1  # .a@1
    assert stmts[1].output_set.version == 1  # ._@1 — independent counter


def test_resolve_types_read_after_write() -> None:
    stmts = _transform_query("node -> .a; .a;").statements
    assert isinstance(stmts[1], ItemStatement)
    assert stmts[1].input_set.version == stmts[0].output_set.version
    assert stmts[1].input_set.content_types == _NODE
    assert stmts[1].output_set.content_types == _NODE


def test_resolve_types_uninitialized_read() -> None:
    result = _transform_query("node(around.foo:100);")
    assert any("Uninitialized" in w.message for w in result.warnings)
    stmt = result.statements[0]
    assert isinstance(stmt, QueryStatement)
    around = next(f for f in stmt.filters if isinstance(f, AroundSetFilter))
    assert around.set_reference.version == 0
    assert around.set_reference.content_types == _NONE


def test_resolve_types_filter_ref_stamped() -> None:
    stmts = _transform_query("node -> .a; node(around.a:100);").statements
    stmt = stmts[1]
    assert isinstance(stmt, QueryStatement)
    around = next(f for f in stmt.filters if isinstance(f, AroundSetFilter))
    assert around.set_reference.version == 1
    assert around.set_reference.content_types == _NODE


def test_resolve_types_if_both_branches_write() -> None:
    # then writes {way}, else writes {relation}; merge = {way, relation}
    stmts = _transform_query("node; if(1) { way; } else { relation; } out;").statements
    assert isinstance(stmts[2], OutStatement)
    assert stmts[2].input_set.version == 2
    assert stmts[2].input_set.content_types == _WAY | _RELATION


def test_resolve_types_if_one_branch_writes() -> None:
    # only then writes {way}; merge includes pre-if {node}
    stmts = _transform_query("node; if(1) { way; } out;").statements
    assert isinstance(stmts[2], OutStatement)
    assert stmts[2].input_set.version == 2
    assert stmts[2].input_set.content_types == _NODE | _WAY


def test_resolve_types_evaluator_ref_stamped() -> None:
    # node -> .a; node(if:a.count(nodes)>0);
    stmts = _transform_query("node -> .a; node(if:a.count(nodes)>0);").statements
    if_filter = stmts[1].filters[0]
    assert isinstance(if_filter, IfFilter)
    assert isinstance(if_filter.evaluator, CompareEvaluator)
    count_expr = if_filter.evaluator.left_operand
    assert isinstance(count_expr, CountEvaluator)
    assert count_expr.input_set.version == 1
    assert count_expr.input_set.content_types == _NODE


def test_resolve_types_for_block() -> None:
    # node -> .a; for .a -> .b (version()==1) { .b out; }
    stmts = _transform_query(
        "node -> .a; for .a -> .b (version()==1) { .b out; }"
    ).statements
    for_stmt = stmts[1]
    assert isinstance(for_stmt, ForStatement)
    assert for_stmt.input_set.version == 1
    assert for_stmt.input_set.content_types == _NODE
    assert for_stmt.output_set.version == 2
    assert for_stmt.output_set.content_types == _NONE
    body_out = for_stmt.body[0]
    assert isinstance(body_out, OutStatement)
    assert body_out.input_set.version == 1
    assert body_out.input_set.content_types == _NODE


def test_resolve_types_union_for_if() -> None:
    query = _transform_query(
        "( node(1); node(2); node(3); ) -> .a;"
        "for .a -> .b (id()==2) {"
        "  if (b.count(nodes) > 1) {"
        "    .b out ids;"
        "    .b -> .c;"
        "  } else {"
        "    .b out;"
        "    .b -> .c;"
        "  }"
        "}"
        ".c out count;"
    )
    assert not query.warnings

    # union members each write to ._ independently; union writes .a
    union = query.statements[0]
    assert isinstance(union, UnionStatement)
    m0, m1, m2 = union.members
    assert isinstance(m0.statement, QueryStatement)
    assert isinstance(m1.statement, QueryStatement)
    assert isinstance(m2.statement, QueryStatement)
    assert m0.statement.output_set.version == 1
    assert m1.statement.output_set.version == 2
    assert m2.statement.output_set.version == 3
    assert union.output_set.version == 1
    assert union.output_set.content_types == _NODE

    # for reads .a@1; iteration variable .b is stamped before body executes
    for_stmt = query.statements[1]
    assert isinstance(for_stmt, ForStatement)
    assert for_stmt.input_set.version == 1
    assert for_stmt.input_set.content_types == _NODE
    assert for_stmt.output_set.version == 2
    assert for_stmt.output_set.content_types == _NONE

    if_stmt = for_stmt.body[0]
    assert isinstance(if_stmt, IfStatement)
    then_out, then_item = if_stmt.then_body
    assert if_stmt.else_body is not None
    else_out, else_item = if_stmt.else_body

    # out statements in both branches read .b@1
    assert isinstance(then_out, OutStatement)
    assert isinstance(else_out, OutStatement)
    assert then_out.input_set.version == 1
    assert then_out.input_set.content_types == _NODE
    assert else_out.input_set.version == 1
    assert else_out.input_set.content_types == _NODE

    # both branches write .b -> .c; each branch gets .c@1 independently,
    # and the if merge also produces .c@1 (first write of .c)
    assert isinstance(then_item, ItemStatement)
    assert isinstance(else_item, ItemStatement)
    assert then_item.input_set.version == 1
    assert then_item.input_set.content_types == _NODE
    assert then_item.output_set.version == 1
    assert then_item.output_set.content_types == _NODE
    assert else_item.input_set.version == 1
    assert else_item.input_set.content_types == _NODE
    assert else_item.output_set.version == 1
    assert else_item.output_set.content_types == _NODE

    # .c out count reads .c@1 produced by the if merge
    c_out = query.statements[2]
    assert isinstance(c_out, OutStatement)
    assert c_out.input_set.version == 1
    assert c_out.input_set.content_types == _NODE


def test_resolve_types_complete_output_set_versioned_in_body() -> None:
    # output set gets a start-of-loop stamp before the body walk, so reads of it
    # inside the body see that version rather than the pre-complete version
    query = _transform_query(
        "node(1) -> .a;"
        "complete .a -> .b {"
        "  .b out ids;"
        "  way -> .b;"
        "  .b out ids;"
        "}"
        ".b out ids;"
    )
    assert not query.warnings
    complete = query.statements[1]
    assert isinstance(complete, CompleteStatement)

    first_out, way_stmt, second_out = complete.body
    assert isinstance(first_out, OutStatement)
    assert isinstance(way_stmt, QueryStatement)
    assert isinstance(second_out, OutStatement)

    # start-of-loop stamp: .b@1 seeded from input set (.a = _NODE)
    assert first_out.input_set.version == 1
    assert first_out.input_set.content_types == _NODE

    # body write: .b@2 (_WAY)
    assert way_stmt.output_set.version == 2
    assert way_stmt.output_set.content_types == _WAY

    # read after body write: .b@2
    assert second_out.input_set.version == 2
    assert second_out.input_set.content_types == _WAY

    # end-of-statement stamp: .b@3; body wrote ways to .b but copy_outward overwrites
    # it — the accumulated output reflects only the input set (.a = _NODE)
    assert complete.output_set.version == 3
    assert complete.output_set.content_types == _NODE

    # post-complete read sees .b@3
    final_out = query.statements[2]
    assert isinstance(final_out, OutStatement)
    assert final_out.input_set.version == 3
    assert final_out.input_set.content_types == _NODE


def test_resolve_types_complete() -> None:
    query = _transform_query(
        "way(689254681);"
        "complete -> .ways {"
        "  > -> .nodes;"
        "  .nodes < -> .parents;"
        '  way.parents["highway"="track"];'
        "}"
        ".ways out ids;"
    )
    assert not query.warnings

    # way query writes ._@1 with _WAY
    way_stmt = query.statements[0]
    assert isinstance(way_stmt, QueryStatement)
    assert way_stmt.output_set.version == 1
    assert way_stmt.output_set.content_types == _WAY

    # complete reads ._@1; start-of-loop stamps .ways@1; end-of-statement stamps .ways@2
    complete = query.statements[1]
    assert isinstance(complete, CompleteStatement)
    assert complete.input_set.version == 1
    assert complete.input_set.content_types == _WAY
    assert complete.output_set.version == 2
    assert complete.output_set.content_types == _WAY

    # body[0]: recurse > on _WAY produces _NODE (way members are nodes)
    recurse_down, recurse_up, way_query = complete.body
    assert isinstance(recurse_down, RecurseStatement)
    assert recurse_down.input_set.version == 1
    assert recurse_down.input_set.content_types == _WAY
    assert recurse_down.output_set.version == 1
    assert recurse_down.output_set.content_types == _NODE

    # body[1]: recurse < on _NODE produces _WR (nodes are members of ways and relations)
    assert isinstance(recurse_up, RecurseStatement)
    assert recurse_up.input_set.version == 1
    assert recurse_up.input_set.content_types == _NODE
    assert recurse_up.output_set.version == 1
    assert recurse_up.output_set.content_types == _WR

    # body[2]: way query intersects _WAY stream with .parents@1 (_WR), writes ._@2
    assert isinstance(way_query, QueryStatement)
    set_filter = next(f for f in way_query.filters if isinstance(f, SetFilter))
    assert set_filter.set_reference.version == 1
    assert set_filter.set_reference.content_types == _WR
    assert way_query.output_set.version == 2
    assert way_query.output_set.content_types == _WAY

    # .ways out ids reads .ways@2 with fully resolved _WAY
    ways_out = query.statements[2]
    assert isinstance(ways_out, OutStatement)
    assert ways_out.input_set.version == 2
    assert ways_out.input_set.content_types == _WAY


def test_resolve_types_complete_named_input() -> None:
    query = _transform_query(
        "way(689254681) -> .seed;"
        "complete .seed -> .ways {"
        "  .seed > -> .nodes;"
        "  .nodes < -> .parents;"
        '  way.parents["highway"="track"] -> .seed;'
        "}"
        ".ways out ids;"
    )
    assert not query.warnings

    # way query writes ._@1 with _WAY
    way_stmt = query.statements[0]
    assert isinstance(way_stmt, QueryStatement)
    assert way_stmt.output_set.version == 1
    assert way_stmt.output_set.content_types == _WAY

    # complete reads .seed@1; start-of-loop stamps .ways@1;
    # end-of-statement stamps .ways@2
    complete = query.statements[1]
    assert isinstance(complete, CompleteStatement)
    assert complete.input_set.version == 1
    assert complete.input_set.content_types == _WAY
    assert complete.output_set.version == 2
    assert complete.output_set.content_types == _WAY

    # body[0]: recurse > on _WAY produces _NODE (way members are nodes)
    recurse_down, recurse_up, way_query = complete.body
    assert isinstance(recurse_down, RecurseStatement)
    assert recurse_down.input_set.version == 1
    assert recurse_down.input_set.content_types == _WAY
    assert recurse_down.output_set.version == 1
    assert recurse_down.output_set.content_types == _NODE

    # body[1]: recurse < on _NODE produces _WR (nodes are members of ways and relations)
    assert isinstance(recurse_up, RecurseStatement)
    assert recurse_up.input_set.version == 1
    assert recurse_up.input_set.content_types == _NODE
    assert recurse_up.output_set.version == 1
    assert recurse_up.output_set.content_types == _WR

    # body[2]: way query intersects _WAY stream with .parents@1 (_WR), writes .seed@2
    assert isinstance(way_query, QueryStatement)
    set_filter = next(f for f in way_query.filters if isinstance(f, SetFilter))
    assert set_filter.set_reference.version == 1
    assert set_filter.set_reference.content_types == _WR
    assert way_query.output_set.version == 2
    assert way_query.output_set.content_types == _WAY

    # .ways out ids reads .ways@2 with fully resolved _WAY
    ways_out = query.statements[2]
    assert isinstance(ways_out, OutStatement)
    assert ways_out.input_set.version == 2
    assert ways_out.input_set.content_types == _WAY


def test_resolve_types_required_types_match_no_warning() -> None:
    # area_set_filter requires {area}; map_to_area produces {area} — no warning
    query = _transform_query("way -> .a; .a map_to_area -> ._; node(area._);")
    assert not query.warnings


def test_resolve_types_required_types_mismatch_area_set_filter() -> None:
    # area_set_filter requires {area}; node produces {node} — warning
    query = _transform_query("node -> ._; node(area._);")
    assert any("requires" in w.message for w in query.warnings)


def test_resolve_types_required_types_mismatch_recurse_filter_w() -> None:
    # recurse_filter(w) set_ref requires {way}; node -> .a produces {node} — warning
    query = _transform_query("node -> .a; node(w.a);")
    assert any("requires" in w.message for w in query.warnings)


def test_resolve_types_required_types_mismatch_pivot_filter() -> None:
    # pivot_filter requires {area}; node -> .a produces {node} — warning
    query = _transform_query("node -> .a; way(pivot.a);")
    assert any("requires" in w.message for w in query.warnings)


def test_resolve_types_required_types_mismatch_uninitialized_set() -> None:
    # area_set_filter requires {area};
    # .foo is uninitialized (_NONE) — warning with "nothing"
    query = _transform_query("node(area.foo);")
    assert any("nothing" in w.message for w in query.warnings)


def test_resolve_types_required_types_mismatch_out() -> None:
    query = _transform_query("out;")
    assert any("nothing" in w.message for w in query.warnings)


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
    filter = _first_filter("nwr[amenity];")
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "amenity"
    assert filter.absent is False
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_tag_filter_exists_area() -> None:
    filter = _first_filter("area[amenity];")
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "amenity"
    assert filter.absent is False
    assert filter.token is not None
    assert filter.output_types == _AREA


def test_tag_filter_absent() -> None:
    filter = _first_filter("nwr[!amenity];")
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "amenity"
    assert filter.absent is True
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_tag_filter_absent_area() -> None:
    filter = _first_filter("area[!amenity];")
    assert isinstance(filter, TagKeyFilter)
    assert filter.key == "amenity"
    assert filter.absent is True
    assert filter.token is not None
    assert filter.output_types == _AREA


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_filter_eq / tag_filter_neq
# ---------------------------------------------------------------------------


def test_tag_filter_eq() -> None:
    filter = _first_filter("nwr[amenity=cafe];")
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "amenity"
    assert filter.op == TagFilterOp.EQ
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_tag_filter_eq_area() -> None:
    filter = _first_filter("area[amenity=cafe];")
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "amenity"
    assert filter.op == TagFilterOp.EQ
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.output_types == _AREA


def test_tag_filter_neq() -> None:
    filter = _first_filter("nwr[amenity!=cafe];")
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "amenity"
    assert filter.op == TagFilterOp.NEQ
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_tag_filter_neq_area() -> None:
    filter = _first_filter("area[amenity!=cafe];")
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "amenity"
    assert filter.op == TagFilterOp.NEQ
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.output_types == _AREA


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_filter_regex / tag_filter_not_regex
# ---------------------------------------------------------------------------


def test_tag_filter_regex() -> None:
    filter = _first_filter('nwr[name~"cafe"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "name"
    assert filter.op == TagFilterOp.REGEX
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_tag_filter_regex_area() -> None:
    filter = _first_filter('area[name~"cafe"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "name"
    assert filter.op == TagFilterOp.REGEX
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.output_types == _AREA


def test_tag_filter_regex_case_insensitive() -> None:
    filter = _first_filter('nwr[name~"cafe",i];')
    assert isinstance(filter, TagValueFilter)
    assert filter.op == TagFilterOp.REGEX
    assert filter.case_insensitive is True
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_tag_filter_regex_case_insensitive_area() -> None:
    filter = _first_filter('area[name~"cafe",i];')
    assert isinstance(filter, TagValueFilter)
    assert filter.op == TagFilterOp.REGEX
    assert filter.case_insensitive is True
    assert filter.token is not None
    assert filter.output_types == _AREA


def test_tag_filter_not_regex() -> None:
    filter = _first_filter('nwr[name!~"cafe"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "name"
    assert filter.op == TagFilterOp.NOT_REGEX
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_tag_filter_not_regex_area() -> None:
    filter = _first_filter('area[name!~"cafe"];')
    assert isinstance(filter, TagValueFilter)
    assert filter.key == "name"
    assert filter.op == TagFilterOp.NOT_REGEX
    assert filter.value == "cafe"
    assert filter.case_insensitive is False
    assert filter.token is not None
    assert filter.output_types == _AREA


def test_tag_filter_not_regex_case_insensitive() -> None:
    filter = _first_filter('nwr[name!~"cafe",i];')
    assert isinstance(filter, TagValueFilter)
    assert filter.op == TagFilterOp.NOT_REGEX
    assert filter.case_insensitive is True
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_tag_filter_not_regex_case_insensitive_area() -> None:
    filter = _first_filter('area[name!~"cafe",i];')
    assert isinstance(filter, TagValueFilter)
    assert filter.op == TagFilterOp.NOT_REGEX
    assert filter.case_insensitive is True
    assert filter.token is not None
    assert filter.output_types == _AREA


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
    filter = _first_filter("nwr(51.5,-0.2,51.6,-0.1);")
    assert isinstance(filter, BboxFilter)
    assert filter.south == "51.5"
    assert filter.west == "-0.2"
    assert filter.north == "51.6"
    assert filter.east == "-0.1"
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_bbox_filter_values_area() -> None:
    filter = _first_filter("area(51.5,-0.2,51.6,-0.1);")
    assert isinstance(filter, BboxFilter)
    assert filter.south == "51.5"
    assert filter.west == "-0.2"
    assert filter.north == "51.6"
    assert filter.east == "-0.1"
    assert filter.token is not None
    assert filter.output_types == _AREA


def test_bbox_filter_inverted_warns() -> None:
    transformer = OverpassTransformer()
    transformer.transform(parse("node(51.6,-0.2,51.5,-0.1);"))
    assert len(transformer.warnings) == 1
    assert "south >= north" in transformer.warnings[0].message


# ---------------------------------------------------------------------------
# OverpassTransformer.id_filter_single / id_filter_list
# ---------------------------------------------------------------------------


def test_id_filter_single() -> None:
    filter = _first_filter("nwr(123);")
    assert isinstance(filter, IdFilter)
    assert filter.ids == [123]
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_id_filter_single_area() -> None:
    filter = _first_filter("area(123);")
    assert isinstance(filter, IdFilter)
    assert filter.ids == [123]
    assert filter.token is not None
    assert filter.output_types == _AREA


def test_id_filter_list() -> None:
    filter = _first_filter("nwr(id:1,2,3);")
    assert isinstance(filter, IdFilter)
    assert filter.ids == [1, 2, 3]
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_id_filter_list_area() -> None:
    filter = _first_filter("area(id:1,2,3);")
    assert isinstance(filter, IdFilter)
    assert filter.ids == [1, 2, 3]
    assert filter.token is not None
    assert filter.output_types == _AREA


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
    filter = _first_filter("nwr(around:100.0,51.5,-0.2,51.6,-0.1);")
    assert isinstance(filter, AroundLineFilter)
    assert filter.radius == "100.0"
    assert [(p.lat, p.lon) for p in filter.points] == [
        ("51.5", "-0.2"),
        ("51.6", "-0.1"),
    ]
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_around_line_filter_area() -> None:
    filter = _first_filter("area(around:100.0,51.5,-0.2,51.6,-0.1);")
    assert isinstance(filter, AroundLineFilter)
    assert filter.radius == "100.0"
    assert [(p.lat, p.lon) for p in filter.points] == [
        ("51.5", "-0.2"),
        ("51.6", "-0.1"),
    ]
    assert filter.token is not None
    assert filter.output_types == _AREA


# ---------------------------------------------------------------------------
# OverpassTransformer.poly_lat_lon (via polygon_filter)
# ---------------------------------------------------------------------------


def test_poly_lat_lon_values() -> None:
    filter = _first_filter('nwr(poly:"51.5 -0.2 51.6 -0.1 51.5 -0.3");')
    assert isinstance(filter, PolygonFilter)
    assert [(p.lat, p.lon) for p in filter.points] == [
        ("51.5", "-0.2"),
        ("51.6", "-0.1"),
        ("51.5", "-0.3"),
    ]
    assert filter.output_types == _NWR


def test_poly_lat_lon_values_area() -> None:
    filter = _first_filter('area(poly:"51.5 -0.2 51.6 -0.1 51.5 -0.3");')
    assert isinstance(filter, PolygonFilter)
    assert [(p.lat, p.lon) for p in filter.points] == [
        ("51.5", "-0.2"),
        ("51.6", "-0.1"),
        ("51.5", "-0.3"),
    ]
    assert filter.output_types == _AREA


# ---------------------------------------------------------------------------
# OverpassTransformer.newer_filter
# ---------------------------------------------------------------------------


def test_newer_filter() -> None:
    filter = _first_filter('nwr(newer:"2024-03-12T11:03:25Z");')
    assert isinstance(filter, NewerFilter)
    assert filter.timestamp.year == 2024
    assert filter.timestamp.month == 3
    assert filter.timestamp.day == 12
    assert filter.token is not None
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
    filter = _first_filter('nwr(user:"alice");')
    assert isinstance(filter, UserFilter)
    assert filter.users == ["alice"]
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_user_filter_multiple() -> None:
    filter = _first_filter('nwr(user:"alice","bob");')
    assert isinstance(filter, UserFilter)
    assert filter.users == ["alice", "bob"]
    assert filter.output_types == _NWR


# ---------------------------------------------------------------------------
# OverpassTransformer.uid_filter
# ---------------------------------------------------------------------------


def test_uid_filter_single() -> None:
    filter = _first_filter("nwr(uid:42);")
    assert isinstance(filter, UidFilter)
    assert filter.uids == [42]
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_uid_filter_multiple() -> None:
    filter = _first_filter("nwr(uid:1,2,3);")
    assert isinstance(filter, UidFilter)
    assert filter.uids == [1, 2, 3]
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
    filter = _first_filter("nwr(area);")
    assert isinstance(filter, AreaSetFilter)
    assert filter.set_reference.name == "_"
    assert filter.set_reference.token is None
    assert filter.set_reference.required_types == frozenset({ElementType.AREA})
    assert filter.token is None
    assert filter.output_types == _NWR


def test_area_set_filter_default_set_area() -> None:
    filter = _first_filter("area(area);")
    assert isinstance(filter, AreaSetFilter)
    assert filter.set_reference.name == "_"
    assert filter.set_reference.token is None
    assert filter.set_reference.required_types == frozenset({ElementType.AREA})
    assert filter.token is None
    assert filter.output_types == _AREA


def test_area_set_filter_explicit_set() -> None:
    filter = _first_filter("nwr(area.foo);")
    assert isinstance(filter, AreaSetFilter)
    assert filter.set_reference.name == "foo"
    assert filter.set_reference.token is not None
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_area_set_filter_explicit_set_area() -> None:
    filter = _first_filter("area(area.foo);")
    assert isinstance(filter, AreaSetFilter)
    assert filter.set_reference.name == "foo"
    assert filter.set_reference.token is not None
    assert filter.token is not None
    assert filter.output_types == _AREA


# ---------------------------------------------------------------------------
# OverpassTransformer.area_id_filter
# ---------------------------------------------------------------------------


def test_area_id_filter() -> None:
    filter = _first_filter("nwr(area:3600000001);")
    assert isinstance(filter, AreaIdFilter)
    assert filter.area_id == 3600000001
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_area_id_filter_area() -> None:
    filter = _first_filter("area(area:3600000001);")
    assert isinstance(filter, AreaIdFilter)
    assert filter.area_id == 3600000001
    assert filter.token is not None
    assert filter.output_types == _AREA


# ---------------------------------------------------------------------------
# OverpassTransformer.recurse_filter
# ---------------------------------------------------------------------------


def test_recurse_filter_w() -> None:
    filter = _first_filter("node(w);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.W
    assert filter.output_types == frozenset({ElementType.NODE})
    assert filter.set_reference.required_types == frozenset({ElementType.WAY})
    assert filter.set_reference.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_r() -> None:
    filter = _first_filter("nwr(r);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.R
    assert filter.output_types == _NWR
    assert filter.set_reference.required_types == frozenset({ElementType.RELATION})
    assert filter.set_reference.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_bn() -> None:
    filter = _first_filter("wr(bn);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.BN
    assert filter.output_types == _WR
    assert filter.set_reference.required_types == frozenset({ElementType.NODE})
    assert filter.set_reference.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_bw() -> None:
    filter = _first_filter("rel(bw);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.BW
    assert filter.output_types == frozenset({ElementType.RELATION})
    assert filter.set_reference.required_types == frozenset({ElementType.WAY})
    assert filter.set_reference.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_br() -> None:
    filter = _first_filter("rel(br);")
    assert isinstance(filter, RecurseFilter)
    assert filter.recurse_type == RecurseFilterType.BR
    assert filter.output_types == frozenset({ElementType.RELATION})
    assert filter.set_reference.required_types == frozenset({ElementType.RELATION})
    assert filter.set_reference.name == "_"
    assert filter.token is not None
    assert filter.role is None


def test_recurse_filter_explicit_set() -> None:
    filter = _first_filter("node(w.foo);")
    assert isinstance(filter, RecurseFilter)
    assert filter.set_reference.name == "foo"
    assert filter.set_reference.token is not None
    assert filter.set_reference.required_types == frozenset({ElementType.WAY})


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
    assert filter.set_reference.name == "_"
    assert filter.set_reference.token is None
    assert filter.set_reference.required_types == frozenset({ElementType.WAY})
    assert filter.min_count == 3
    assert filter.max_count == 3
    assert filter.exact is True
    assert filter.output_types == frozenset({ElementType.NODE})
    assert filter.token is not None


def test_way_count_filter_named_set() -> None:
    filter = _first_filter("node(way_cnt.foo:3);")
    assert isinstance(filter, WayCountFilter)
    assert filter.set_reference.name == "foo"
    assert filter.set_reference.token is not None
    assert filter.set_reference.required_types == frozenset({ElementType.WAY})


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
    assert filter.output_types == frozenset()


# ---------------------------------------------------------------------------
# OverpassTransformer.pivot_filter
# ---------------------------------------------------------------------------


def test_pivot_filter_default_set() -> None:
    filter = _first_filter("wr(pivot);")
    assert isinstance(filter, PivotFilter)
    assert filter.set_reference.name == "_"
    assert filter.set_reference.token is None
    assert filter.set_reference.required_types == frozenset({ElementType.AREA})
    assert filter.output_types == _WR
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
    filter = _first_filter("nwr(if:1);")
    assert isinstance(filter, IfFilter)
    assert isinstance(filter.evaluator, Evaluator)
    assert filter.token is not None
    assert filter.output_types == _NWR


def test_if_filter_area() -> None:
    filter = _first_filter("area(if:1);")
    assert isinstance(filter, IfFilter)
    assert isinstance(filter.evaluator, Evaluator)
    assert filter.token is not None
    assert filter.output_types == _AREA


# ---------------------------------------------------------------------------
# OverpassTransformer.set_assignment
# ---------------------------------------------------------------------------

# set_assignment is a passthrough; tested via query_stmt

# ---------------------------------------------------------------------------
# OverpassTransformer.statement
# ---------------------------------------------------------------------------


def _statement(text: str) -> Statement:
    stmt = _transform_query(text).statements[0]
    assert isinstance(stmt, Statement)
    return stmt


def test_statement() -> None:
    stmt = _statement("node;")
    assert isinstance(stmt, Statement)


# ---------------------------------------------------------------------------
# OverpassTransformer.query_stmt
# ---------------------------------------------------------------------------


def _query_stmt(text: str) -> QueryStatement:
    stmt = _transform_query(text).statements[0]
    assert isinstance(stmt, QueryStatement)
    return stmt


def test_query_stmt_node() -> None:
    stmt = _query_stmt("node;")
    assert stmt.element_types == frozenset({ElementType.NODE})
    assert stmt.filters == []
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


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
    assert stmt.output_set.name == "x"


def test_query_stmt_no_output_set() -> None:
    stmt = _query_stmt("node[amenity=cafe];")
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_query_stmt_output_types() -> None:
    stmt = _query_stmt("node;")
    warnings: list[Warning] = list()
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NODE
    assert not warnings


def test_query_stmt_output_mismatch() -> None:
    stmt = _query_stmt("area(uid:1);")
    warnings: list[Warning] = list()
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NONE
    assert warnings


def test_query_stmt_output_filter_mismatch() -> None:
    stmt = _query_stmt("node(w)(bw);")
    warnings: list[Warning] = list()
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NONE
    assert warnings


def test_query_stmt_output_indefinite() -> None:
    stmt = _query_stmt("node.a;")
    set_filter = next(f for f in stmt.filters if isinstance(f, SetFilter))
    set_filter.set_reference.content_types = None
    warnings: list[Warning] = list()
    output_types = stmt.get_output_types(warnings)
    assert output_types is None
    assert not warnings


def test_query_stmt_output_set_filter_unassigned() -> None:
    query = _transform_query("node.a;")
    assert query.warnings
    stmt = query.statements[0]
    assert isinstance(stmt, QueryStatement)
    assert stmt.output_set.content_types == _NONE


def test_query_stmt_output_set_filter_assigned() -> None:
    stmts = _transform_query("node -> .a; node.a;").statements
    assert isinstance(stmts[1], QueryStatement)
    assert stmts[1].output_set.content_types == _NODE


# ---------------------------------------------------------------------------
# OverpassTransformer.block_body
# ---------------------------------------------------------------------------

# block_body is a passthrough; tested via foreach/for/complete body tests

# ---------------------------------------------------------------------------
# OverpassTransformer.foreach_stmt
# ---------------------------------------------------------------------------


def _foreach_stmt(text: str) -> ForeachStatement:
    stmt = _transform_query(text).statements[0]
    assert isinstance(stmt, ForeachStatement)
    return stmt


def test_foreach_default_input_output() -> None:
    stmt = _foreach_stmt("foreach { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_foreach_explicit_input_output() -> None:
    stmt = _foreach_stmt("foreach .x -> .y { node; }")
    assert stmt.input_set.name == "x"
    assert isinstance(stmt.input_set.token, Token)
    assert stmt.output_set.name == "y"
    assert isinstance(stmt.output_set.token, Token)


def test_foreach_body() -> None:
    stmt = _foreach_stmt("foreach { node[amenity=cafe]; node[amenity=parking]; }")
    assert len(stmt.body) == 2


def test_foreach_get_output_types_indefinite() -> None:
    stmt = _foreach_stmt("foreach .x -> .a { out; }")
    stmt.input_set.content_types = None
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) is None
    assert not warnings


def test_foreach_get_output_types_unassigned() -> None:
    query = _transform_query("foreach .x -> .a { out; }")
    assert query.warnings
    stmt = query.statements[0]
    assert isinstance(stmt, ForeachStatement)
    assert stmt.input_set.content_types == _NONE
    assert stmt.output_set.content_types == _NONE


def test_foreach_get_output_types_assigned() -> None:
    stmts = _transform_query("node -> .x; foreach .x -> .a { out; }").statements
    stmt = stmts[1]
    assert isinstance(stmt, ForeachStatement)
    assert stmt.input_set.content_types == _NODE
    assert stmt.output_set.content_types == _NONE


def test_foreach_get_output_types_concrete() -> None:
    stmt = _foreach_stmt("foreach .x -> .a { out; }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE
    assert not warnings


# ---------------------------------------------------------------------------
# OverpassTransformer.for_stmt
# ---------------------------------------------------------------------------


def _for_stmt(text: str) -> ForStatement:
    stmt = _transform_query(text).statements[0]
    assert isinstance(stmt, ForStatement)
    return stmt


def test_for_default_input_output() -> None:
    stmt = _for_stmt("for(1) { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_for_explicit_input_output() -> None:
    stmt = _for_stmt("for .x -> .y (1) { node; }")
    assert stmt.input_set.name == "x"
    assert isinstance(stmt.input_set.token, Token)
    assert stmt.output_set.name == "y"
    assert isinstance(stmt.output_set.token, Token)


def test_for_evaluator() -> None:
    stmt = _for_stmt("for(1) { node; }")
    assert isinstance(stmt.evaluator, Evaluator)


def test_for_body() -> None:
    stmt = _for_stmt("for(1) { node[amenity=cafe]; node[amenity=parking]; }")
    assert len(stmt.body) == 2


def test_for_get_output_types_indefinite() -> None:
    stmt = _for_stmt("for .x -> .a (1) { out; }")
    stmt.input_set.content_types = None
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) is None
    assert not warnings


def test_for_get_output_types_unassigned() -> None:
    query = _transform_query("for .x -> .a (1) { out; }")
    assert query.warnings
    stmt = query.statements[0]
    assert isinstance(stmt, ForStatement)
    assert stmt.input_set.content_types == _NONE
    assert stmt.output_set.content_types == _NONE


def test_for_get_output_types_assigned() -> None:
    query = _transform_query("node -> .x; for .x -> .a (1) { .a out; }")
    assert not query.warnings
    stmt = query.statements[1]
    assert stmt.input_set.content_types == _NODE
    assert stmt.output_set.content_types == _NONE


# ---------------------------------------------------------------------------
# OverpassTransformer.complete_stmt
# ---------------------------------------------------------------------------


def _complete_stmt(text: str) -> CompleteStatement:
    stmt = _transform_query(text).statements[0]
    assert isinstance(stmt, CompleteStatement)
    return stmt


def test_complete_default_input_output() -> None:
    stmt = _complete_stmt("complete { node; }")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_complete_explicit_input_output() -> None:
    stmt = _complete_stmt("complete .x -> .y { node; }")
    assert stmt.input_set.name == "x"
    assert isinstance(stmt.input_set.token, Token)
    assert stmt.output_set.name == "y"
    assert isinstance(stmt.output_set.token, Token)


def test_complete_max_iterations() -> None:
    stmt = _complete_stmt("complete(5) { node; }")
    assert stmt.max_iterations == 5


def test_complete_no_max_iterations() -> None:
    stmt = _complete_stmt("complete { node; }")
    assert stmt.max_iterations is None


def test_complete_body() -> None:
    stmt = _complete_stmt("complete { node[amenity=cafe]; node[amenity=parking]; }")
    assert len(stmt.body) == 2


def test_complete_get_output_types_indefinite_input() -> None:
    stmt = _complete_stmt("complete { node; }")
    stmt.input_set.content_types = None
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) is None
    assert not warnings


def test_complete_get_output_types_input_unassigned() -> None:
    query = _transform_query("complete { node; }")
    assert query.warnings
    stmt = query.statements[0]
    assert isinstance(stmt, CompleteStatement)
    assert stmt.input_set.content_types == _NONE
    assert stmt.output_set.content_types == _NODE


def test_complete_get_output_types_input_assigned() -> None:
    query = _transform_query("way; complete { node; }")
    assert not query.warnings
    stmt = query.statements[1]
    assert isinstance(stmt, CompleteStatement)
    assert stmt.input_set.content_types == _WAY
    assert stmt.output_set.content_types == _WAY | _NODE


def test_complete_get_output_types_no_body_contribution() -> None:
    stmt = _complete_stmt("complete { out; }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE
    assert not warnings


def test_complete_get_output_types_indefinite_body() -> None:
    stmt = _complete_stmt("complete { .a; }")
    stmt.input_set.content_types = _NODE
    item_stmt = stmt.body[0]
    assert isinstance(item_stmt, ItemStatement)
    item_stmt.input_set.content_types = None
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) is None
    assert not warnings


def test_complete_get_output_types_body_unassigned() -> None:
    stmts = _transform_query("node; complete { .a; }").statements
    stmt = stmts[1]
    assert isinstance(stmt, CompleteStatement)
    assert stmt.input_set.content_types == _NODE
    assert stmt.output_set.content_types == _NODE


def test_complete_get_output_types_body_assigned() -> None:
    stmts = _transform_query("way -> .a; node; complete { .a; }").statements
    stmt = stmts[2]
    assert isinstance(stmt, CompleteStatement)
    assert stmt.input_set.content_types == _NODE
    assert stmt.output_set.content_types == _NODE | _WAY


def test_complete_get_output_types_body_leaf() -> None:
    stmt = _complete_stmt("complete { way; }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE | _WAY
    assert not warnings


def test_complete_get_output_types_foreach_output_is_accum() -> None:
    # foreach output_set == accum; loop exit clears accum, no body contribution
    stmt = _complete_stmt("complete { foreach { way; } }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE
    assert not warnings


def test_complete_get_output_types_foreach_body_writes_accum() -> None:
    # foreach output_set != accum; body write to ._ persists
    stmt = _complete_stmt("complete { foreach -> .each { way; } }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE | _WAY
    assert not warnings


def test_complete_get_output_types_for_output_is_accum() -> None:
    # for output_set == accum; loop exit clears accum, no body contribution
    stmt = _complete_stmt("complete { for(1) { way; } }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE
    assert not warnings


def test_complete_get_output_types_for_body_writes_accum() -> None:
    # for output_set != accum; body write to ._ persists
    stmt = _complete_stmt("complete { for -> .group (1) { way; } }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE | _WAY
    assert not warnings


def test_complete_get_output_types_if_branch() -> None:
    stmt = _complete_stmt("complete { if(1) { way; } }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE | _WAY
    assert not warnings


def test_complete_get_output_types_if_else_branches() -> None:
    stmt = _complete_stmt("complete { if(1) { way; } else { relation; } }")
    stmt.input_set.content_types = _NODE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NWR
    assert not warnings


def test_complete_get_output_types_nested_complete() -> None:
    stmt = _complete_stmt("complete { complete { way; } }")
    stmt.input_set.content_types = _NODE
    inner = stmt.body[0]
    assert isinstance(inner, CompleteStatement)
    inner.input_set.content_types = _NONE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE | _WAY
    assert not warnings


def test_complete_get_output_types_union_to_underscore() -> None:
    stmt = _complete_stmt("complete { ( node; way; ); }")
    stmt.input_set.content_types = _NONE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NODE | _WAY
    assert not warnings


def test_complete_get_output_types_union_to_named_set() -> None:
    # union -> .found propagates inner ._ as a side effect; last member (way) wins
    stmt = _complete_stmt("complete { ( node; way; ) -> .found; }")
    stmt.input_set.content_types = _NONE
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _WAY
    assert not warnings


# ---------------------------------------------------------------------------
# OverpassTransformer.if_stmt
# ---------------------------------------------------------------------------


def _if_stmt(text: str) -> IfStatement:
    stmt = _transform_query(text).statements[0]
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


def test_if_get_output_types() -> None:
    stmt = _if_stmt("if(1) { node; }")
    warnings: list[Warning] = []
    assert stmt.get_output_types(warnings) == _NONE
    assert not warnings


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
    stmt = _transform_query(text).statements[0]
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


def test_union_member_statement_and_token() -> None:
    stmt = _union_stmt("( node(1); node(2); );")
    assert isinstance(stmt.members[0].statement, QueryStatement)
    assert stmt.token is stmt.members[0].statement.token


def test_union_output_set() -> None:
    stmt = _union_stmt("( node(1); node(2); ) -> .x;")
    assert stmt.output_set.name == "x"
    assert stmt.output_set.token is not None


def test_union_no_output_set() -> None:
    stmt = _union_stmt("( node(1); node(2); );")
    assert stmt.output_set.name == "_"
    assert stmt.output_set.token is None


def test_union_empty() -> None:
    stmt = _union_stmt("();")
    assert len(stmt.members) == 0
    assert stmt.token is None


def test_union_empty_token_with_output_set() -> None:
    stmt = _union_stmt("() -> .x;")
    assert len(stmt.members) == 0
    assert stmt.output_set.name == "x"
    assert stmt.output_set.token is not None


def test_union_stmt_output_types() -> None:
    stmt = _union_stmt("( node(1); way(1); );")
    warnings: list[Warning] = []
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NODE | _WAY
    assert not warnings


def test_union_stmt_output_types_empty() -> None:
    stmt = _union_stmt("();")
    warnings: list[Warning] = []
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NONE
    assert warnings


def test_union_stmt_output_types_indefinite_member() -> None:
    stmt = _union_stmt("( node.a; );")
    member_stmt = stmt.members[0].statement
    assert isinstance(member_stmt, QueryStatement)
    set_filter = next(f for f in member_stmt.filters if isinstance(f, SetFilter))
    set_filter.set_reference.content_types = None
    warnings: list[Warning] = []
    output_types = stmt.get_output_types(warnings)
    assert output_types is None
    assert not warnings


def test_union_stmt_output_types_member_unassigned() -> None:
    query = _transform_query("( node.a; );")
    assert query.warnings
    stmt = query.statements[0]
    assert isinstance(stmt, UnionStatement)
    assert stmt.output_set.content_types == _NONE


def test_union_stmt_output_types_member_assigned() -> None:
    stmts = _transform_query("node -> .a; ( node.a; );").statements
    stmt = stmts[1]
    assert isinstance(stmt, UnionStatement)
    assert stmt.output_set.content_types == _NODE


def test_union_stmt_output_types_difference_excluded() -> None:
    stmt = _union_stmt("( node(1); - way(1); );")
    warnings: list[Warning] = []
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NODE
    assert not warnings


def test_union_stmt_output_types_difference_indefinite() -> None:
    stmt = _union_stmt("( node(1); - node.a; );")
    diff_stmt = stmt.members[1].statement
    assert isinstance(diff_stmt, QueryStatement)
    set_filter = next(f for f in diff_stmt.filters if isinstance(f, SetFilter))
    set_filter.set_reference.content_types = None
    warnings: list[Warning] = []
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NODE
    assert not warnings


def test_union_stmt_output_types_difference_unassigned() -> None:
    query = _transform_query("( node(1); - node.a; );")
    assert query.warnings
    stmt = query.statements[0]
    assert isinstance(stmt, UnionStatement)
    assert stmt.output_set.content_types == _NODE


def test_union_stmt_output_types_difference_assigned() -> None:
    stmts = _transform_query("node -> .a; ( node(1); - node.a; );").statements
    stmt = stmts[1]
    assert isinstance(stmt, UnionStatement)
    assert stmt.output_set.content_types == _NODE


def test_union_stmt_output_types_difference_warning() -> None:
    stmt = _union_stmt("( node(1); - area(uid:1); );")
    warnings: list[Warning] = []
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NODE
    assert warnings


def test_union_stmt_output_types_all_difference() -> None:
    stmt = _union_stmt("( - node(1); );")
    warnings: list[Warning] = []
    output_types = stmt.get_output_types(warnings)
    assert output_types == _NONE
    assert warnings


# ---------------------------------------------------------------------------
# OverpassTransformer.item_stmt
# ---------------------------------------------------------------------------


def _item_stmt(text: str) -> ItemStatement:
    stmt = _transform_query(text).statements[0]
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
    stmt = _transform_query(text).statements[0]
    assert isinstance(stmt, OutStatement)
    return stmt


def test_out_default() -> None:
    stmt = _out_stmt("out;")
    assert stmt.input_set.name == "_"
    assert stmt.input_set.token is None
    assert stmt.count is False
    assert stmt.debug is False
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


def test_out_debug() -> None:
    stmt = _out_stmt("out debug;")
    assert stmt.debug is True
    assert stmt.count is False
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
    with pytest.raises(UnsupportedFeatureError):
        _out_stmt("out qt;")


def test_out_sort_asc() -> None:
    stmt = _out_stmt("out asc;")
    assert stmt.sort_order == OutSortOrder.ASC


def test_out_limit() -> None:
    stmt = _out_stmt("out 10;")
    assert stmt.limit == 10


def test_out_ids_geom_downgrades_to_bb() -> None:
    # Overpass quirk: `ids geom` produces bb-only output, not full geometry.
    stmt = _out_stmt("out ids geom;")
    assert stmt.verbosity == OutVerbosity.IDS
    assert stmt.geom is False
    assert stmt.bb is True


def test_out_tags_geom_downgrades_to_bb() -> None:
    # Overpass quirk: `tags geom` produces bb-only output, not full geometry.
    stmt = _out_stmt("out tags geom;")
    assert stmt.verbosity == OutVerbosity.TAGS
    assert stmt.geom is False
    assert stmt.bb is True


def test_out_skel_geom_keeps_geom() -> None:
    stmt = _out_stmt("out skel geom;")
    assert stmt.verbosity == OutVerbosity.SKEL
    assert stmt.geom is True
    assert stmt.bb is False


def test_out_body_geom_keeps_geom() -> None:
    stmt = _out_stmt("out body geom;")
    assert stmt.verbosity == OutVerbosity.BODY
    assert stmt.geom is True
    assert stmt.bb is False


def test_out_meta_geom_keeps_geom() -> None:
    stmt = _out_stmt("out meta geom;")
    assert stmt.verbosity == OutVerbosity.META
    assert stmt.geom is True
    assert stmt.bb is False


def test_out_verbosity_and_sort() -> None:
    stmt = _out_stmt("out meta asc;")
    assert stmt.verbosity == OutVerbosity.META
    assert stmt.sort_order == OutSortOrder.ASC


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


def test_out_count_with_debug_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out count debug;")


def test_out_debug_with_verbosity_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out debug body;")


def test_out_debug_with_geom_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out debug geom;")


def test_out_debug_with_bb_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out debug bb;")


def test_out_debug_with_center_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out debug center;")


def test_out_debug_with_sort_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out debug qt;")


def test_out_debug_with_limit_raises() -> None:
    with pytest.raises(QueryError):
        _out_stmt("out debug 5;")


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
    stmt = _transform_query(text).statements[0]
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
    stmt = _transform_query(text).statements[0]
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
    stmt = _transform_query(text).statements[0]
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
    assert isinstance(expr, TernaryEvaluator)
    assert isinstance(expr.condition, Evaluator)
    assert isinstance(expr.true_expression, Evaluator)
    assert isinstance(expr.false_expression, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.or_expr
# ---------------------------------------------------------------------------


def test_or_expr() -> None:
    expr = _evaluator("1 || 0")
    assert isinstance(expr, BinaryEvaluator)
    assert expr.operator == BinaryOperator.OR
    assert len(expr.operands) == 2


def test_or_expr_repeated() -> None:
    expr = _evaluator("1 || 0 || 1")
    assert isinstance(expr, BinaryEvaluator)
    assert expr.operator == BinaryOperator.OR
    assert len(expr.operands) == 3


# ---------------------------------------------------------------------------
# OverpassTransformer.and_expr
# ---------------------------------------------------------------------------


def test_and_expr() -> None:
    expr = _evaluator("1 && 0")
    assert isinstance(expr, BinaryEvaluator)
    assert expr.operator == BinaryOperator.AND
    assert len(expr.operands) == 2


def test_and_expr_repeated() -> None:
    expr = _evaluator("1 && 0 && 1")
    assert isinstance(expr, BinaryEvaluator)
    assert expr.operator == BinaryOperator.AND
    assert len(expr.operands) == 3


# ---------------------------------------------------------------------------
# OverpassTransformer.not_expr
# ---------------------------------------------------------------------------


def test_not_expr() -> None:
    expr = _evaluator("!1")
    assert isinstance(expr, UnaryEvaluator)
    assert expr.operator == UnaryOperator.NOT
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.compare_expr
# ---------------------------------------------------------------------------


def test_compare_expr_equal() -> None:
    expr = _evaluator("1 == 2")
    assert isinstance(expr, CompareEvaluator)
    assert expr.operator == CompareOperator.EQUAL


def test_compare_expr_not_equal() -> None:
    expr = _evaluator("1 != 2")
    assert isinstance(expr, CompareEvaluator)
    assert expr.operator == CompareOperator.NOT_EQUAL


def test_compare_expr_less_than() -> None:
    expr = _evaluator("1 < 2")
    assert isinstance(expr, CompareEvaluator)
    assert expr.operator == CompareOperator.LESS_THAN


def test_compare_expr_greater_than() -> None:
    expr = _evaluator("1 > 2")
    assert isinstance(expr, CompareEvaluator)
    assert expr.operator == CompareOperator.GREATER_THAN


def test_compare_expr_less_than_or_equal() -> None:
    expr = _evaluator("1 <= 2")
    assert isinstance(expr, CompareEvaluator)
    assert expr.operator == CompareOperator.LESS_THAN_OR_EQUAL


def test_compare_expr_greater_than_or_equal() -> None:
    expr = _evaluator("1 >= 2")
    assert isinstance(expr, CompareEvaluator)
    assert expr.operator == CompareOperator.GREATER_THAN_OR_EQUAL


def test_compare_expr_operands() -> None:
    expr = _evaluator("1 == 2")
    assert isinstance(expr, CompareEvaluator)
    assert isinstance(expr.left_operand, Evaluator)
    assert isinstance(expr.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.add_expr
# ---------------------------------------------------------------------------


def test_add_expr_add() -> None:
    expr = _evaluator("1 + 2")
    assert isinstance(expr, AddEvaluator)
    assert expr.operator == AddOperator.ADD


def test_add_expr_subtract() -> None:
    expr = _evaluator("1 - 2")
    assert isinstance(expr, AddEvaluator)
    assert expr.operator == AddOperator.SUBTRACT


def test_add_expr_operands() -> None:
    expr = _evaluator("1 + 2")
    assert isinstance(expr, AddEvaluator)
    assert isinstance(expr.left_operand, Evaluator)
    assert isinstance(expr.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.mul_expr
# ---------------------------------------------------------------------------


def test_mul_expr_multiply() -> None:
    expr = _evaluator("2 * 3")
    assert isinstance(expr, MultiplyEvaluator)
    assert expr.operator == MultiplyOperator.MULTIPLY


def test_mul_expr_divide() -> None:
    expr = _evaluator("6 / 2")
    assert isinstance(expr, MultiplyEvaluator)
    assert expr.operator == MultiplyOperator.DIVIDE


def test_mul_expr_operands() -> None:
    expr = _evaluator("2 * 3")
    assert isinstance(expr, MultiplyEvaluator)
    assert isinstance(expr.left_operand, Evaluator)
    assert isinstance(expr.right_operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.unary_expr
# ---------------------------------------------------------------------------


def test_unary_expr() -> None:
    expr = _evaluator("-1")
    assert isinstance(expr, UnaryEvaluator)
    assert expr.operator == UnaryOperator.NEGATE
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.literal_expr
# ---------------------------------------------------------------------------


def test_literal_expr_number() -> None:
    expr = _evaluator("42")
    assert isinstance(expr, LiteralEvaluator)
    assert expr.value == "42"


def test_literal_expr_string() -> None:
    expr = _evaluator('"foo"')
    assert isinstance(expr, LiteralEvaluator)
    assert expr.value == "foo"


# ---------------------------------------------------------------------------
# OverpassTransformer.id_expr
# ---------------------------------------------------------------------------


def test_id_expr() -> None:
    expr = _evaluator("id()")
    assert isinstance(expr, MetadataEvaluator)
    assert expr.attribute == MetadataAttribute.ID


# ---------------------------------------------------------------------------
# OverpassTransformer.type_expr
# ---------------------------------------------------------------------------


def test_type_expr() -> None:
    expr = _evaluator("type()")
    assert isinstance(expr, MetadataEvaluator)
    assert expr.attribute == MetadataAttribute.TYPE


# ---------------------------------------------------------------------------
# OverpassTransformer.tag_value_expr
# ---------------------------------------------------------------------------


def test_tag_value_expr() -> None:
    expr = _evaluator('t["name"]')
    assert isinstance(expr, TagValueEvaluator)
    assert isinstance(expr.evaluator, LiteralEvaluator)


def test_tag_value_expr_dynamic_raises() -> None:
    with pytest.raises(UnsupportedFeatureError):
        _evaluator('t["prefix" + "suffix"]')


# ---------------------------------------------------------------------------
# OverpassTransformer.is_tag_expr
# ---------------------------------------------------------------------------


def test_is_tag_expr() -> None:
    expr = _evaluator("is_tag(name)")
    assert isinstance(expr, IsTagEvaluator)
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
    assert isinstance(expr, MetadataEvaluator)
    assert expr.attribute == MetadataAttribute.VERSION
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.timestamp_expr
# ---------------------------------------------------------------------------


def test_timestamp_expr() -> None:
    expr = _evaluator("timestamp()")
    assert isinstance(expr, MetadataEvaluator)
    assert expr.attribute == MetadataAttribute.TIMESTAMP
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.changeset_expr
# ---------------------------------------------------------------------------


def test_changeset_expr() -> None:
    expr = _evaluator("changeset()")
    assert isinstance(expr, MetadataEvaluator)
    assert expr.attribute == MetadataAttribute.CHANGESET
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.uid_expr
# ---------------------------------------------------------------------------


def test_uid_expr() -> None:
    expr = _evaluator("uid()")
    assert isinstance(expr, MetadataEvaluator)
    assert expr.attribute == MetadataAttribute.UID
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.user_expr
# ---------------------------------------------------------------------------


def test_user_expr() -> None:
    expr = _evaluator("user()")
    assert isinstance(expr, MetadataEvaluator)
    assert expr.attribute == MetadataAttribute.USER
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.count_tags_expr
# ---------------------------------------------------------------------------


def test_count_tags_expr() -> None:
    expr = _evaluator("count_tags()")
    assert isinstance(expr, CountTagsEvaluator)
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.count_members_expr
# ---------------------------------------------------------------------------


def test_count_members_expr() -> None:
    expr = _evaluator("count_members()")
    assert isinstance(expr, CountMembersEvaluator)
    assert expr.distinct is False
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.count_distinct_members_expr
# ---------------------------------------------------------------------------


def test_count_distinct_members_expr() -> None:
    expr = _evaluator("count_distinct_members()")
    assert isinstance(expr, CountMembersEvaluator)
    assert expr.distinct is True
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.count_by_role_expr
# ---------------------------------------------------------------------------


def test_count_by_role_expr() -> None:
    expr = _evaluator('count_by_role("outer")')
    assert isinstance(expr, CountByRoleEvaluator)
    assert isinstance(expr.role, LiteralEvaluator)
    assert expr.distinct is False
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.count_distinct_by_role_expr
# ---------------------------------------------------------------------------


def test_count_distinct_by_role_expr() -> None:
    expr = _evaluator('count_distinct_by_role("outer")')
    assert isinstance(expr, CountByRoleEvaluator)
    assert isinstance(expr.role, LiteralEvaluator)
    assert expr.distinct is True
    assert expr.token is not None


# ---------------------------------------------------------------------------
# OverpassTransformer.is_closed_expr
# ---------------------------------------------------------------------------


def test_is_closed_expr() -> None:
    expr = _evaluator("is_closed()")
    assert isinstance(expr, IsClosedEvaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.lat_expr
# ---------------------------------------------------------------------------


def test_lat_expr() -> None:
    expr = _evaluator("lat()")
    assert isinstance(expr, CoordinateEvaluator)
    assert expr.axis == CoordinateAxis.LAT


# ---------------------------------------------------------------------------
# OverpassTransformer.lon_expr
# ---------------------------------------------------------------------------


def test_lon_expr() -> None:
    expr = _evaluator("lon()")
    assert isinstance(expr, CoordinateEvaluator)
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
    assert isinstance(expr, LengthEvaluator)


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


def test_unique_expr() -> None:
    expr = _evaluator('u(t["name"])')
    assert isinstance(expr, UniqueEvaluator)
    assert expr.input_set.name == "_"
    assert isinstance(expr.evaluator, TagValueEvaluator)


def test_unique_expr_with_set() -> None:
    expr = _evaluator('a.u(t["name"])')
    assert isinstance(expr, UniqueEvaluator)
    assert expr.input_set.name == "a"
    assert isinstance(expr.evaluator, TagValueEvaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.min_expr
# ---------------------------------------------------------------------------


def test_min_expr() -> None:
    expr = _evaluator('min(t["ele"])')
    assert isinstance(expr, MinMaxEvaluator)
    assert expr.operator == AggregateOperator.MIN
    assert expr.input_set.name == "_"
    assert isinstance(expr.evaluator, TagValueEvaluator)


def test_min_expr_with_set() -> None:
    expr = _evaluator('a.min(t["ele"])')
    assert isinstance(expr, MinMaxEvaluator)
    assert expr.operator == AggregateOperator.MIN
    assert expr.input_set.name == "a"
    assert isinstance(expr.evaluator, TagValueEvaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.max_expr
# ---------------------------------------------------------------------------


def test_max_expr() -> None:
    expr = _evaluator('max(t["ele"])')
    assert isinstance(expr, MinMaxEvaluator)
    assert expr.operator == AggregateOperator.MAX
    assert expr.input_set.name == "_"
    assert isinstance(expr.evaluator, TagValueEvaluator)


def test_max_expr_with_set() -> None:
    expr = _evaluator('a.max(t["ele"])')
    assert isinstance(expr, MinMaxEvaluator)
    assert expr.operator == AggregateOperator.MAX
    assert expr.input_set.name == "a"
    assert isinstance(expr.evaluator, TagValueEvaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.sum_expr
# ---------------------------------------------------------------------------


def test_sum_expr() -> None:
    expr = _evaluator('sum(t["ele"])')
    assert isinstance(expr, SumEvaluator)
    assert expr.input_set.name == "_"
    assert isinstance(expr.evaluator, TagValueEvaluator)


def test_sum_expr_with_set() -> None:
    expr = _evaluator('a.sum(t["ele"])')
    assert isinstance(expr, SumEvaluator)
    assert expr.input_set.name == "a"
    assert isinstance(expr.evaluator, TagValueEvaluator)


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
    assert isinstance(expr, CountEvaluator)
    assert expr.count_type == CountType.NODES
    assert expr.input_set.name == "_"
    assert expr.input_set.token is None


def test_count_ways() -> None:
    expr = _evaluator("count(ways)")
    assert isinstance(expr, CountEvaluator)
    assert expr.count_type == CountType.WAYS
    assert expr.input_set.name == "_"
    assert expr.input_set.token is None


def test_count_relations() -> None:
    expr = _evaluator("count(relations)")
    assert isinstance(expr, CountEvaluator)
    assert expr.count_type == CountType.RELATIONS
    assert expr.input_set.name == "_"
    assert expr.input_set.token is None


def test_count_nw() -> None:
    expr = _evaluator("count(nw)")
    assert isinstance(expr, CountEvaluator)
    assert expr.count_type == CountType.NW


def test_count_wr() -> None:
    expr = _evaluator("count(wr)")
    assert isinstance(expr, CountEvaluator)
    assert expr.count_type == CountType.WR


def test_count_nr() -> None:
    expr = _evaluator("count(nr)")
    assert isinstance(expr, CountEvaluator)
    assert expr.count_type == CountType.NR


def test_count_nwr() -> None:
    expr = _evaluator("count(nwr)")
    assert isinstance(expr, CountEvaluator)
    assert expr.count_type == CountType.NWR


def test_count_with_set() -> None:
    expr = _evaluator("a.count(nodes)")
    assert isinstance(expr, CountEvaluator)
    assert expr.count_type == CountType.NODES
    assert isinstance(expr.input_set, SetReference)
    assert expr.input_set.name == "a"


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
    assert isinstance(result, ValEvaluator)
    assert result.set_reference.name == "a"
    assert isinstance(result.set_reference.token, Token)


# ---------------------------------------------------------------------------
# OverpassTransformer.number_expr
# ---------------------------------------------------------------------------


def test_number_expr() -> None:
    expr = _evaluator('number(t["ele"])')
    assert isinstance(expr, ConversionEvaluator)
    assert expr.function == ConversionFunction.NUMBER
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.date_expr
# ---------------------------------------------------------------------------


def test_date_expr() -> None:
    expr = _evaluator('date(t["start_date"])')
    assert isinstance(expr, ConversionEvaluator)
    assert expr.function == ConversionFunction.DATE


# ---------------------------------------------------------------------------
# OverpassTransformer.suffix_expr
# ---------------------------------------------------------------------------


def test_suffix_expr() -> None:
    expr = _evaluator('suffix(t["ele"])')
    assert isinstance(expr, SuffixEvaluator)
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.abs_expr
# ---------------------------------------------------------------------------


def test_abs_expr() -> None:
    expr = _evaluator("abs(-1)")
    assert isinstance(expr, AbsEvaluator)
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.is_number_expr
# ---------------------------------------------------------------------------


def test_is_number_expr() -> None:
    expr = _evaluator('is_number(t["ele"])')
    assert isinstance(expr, TypeCheckEvaluator)
    assert expr.function == TypeCheckFunction.IS_NUMBER
    assert isinstance(expr.operand, Evaluator)


# ---------------------------------------------------------------------------
# OverpassTransformer.is_date_expr
# ---------------------------------------------------------------------------


def test_is_date_expr() -> None:
    expr = _evaluator('is_date(t["start_date"])')
    assert isinstance(expr, TypeCheckEvaluator)
    assert expr.function == TypeCheckFunction.IS_DATE


# ---------------------------------------------------------------------------
# _resolve_element_contexts — target_set stamping
# ---------------------------------------------------------------------------


def test_metadata_target_set_stamped() -> None:
    expr = _evaluator("id()")
    assert isinstance(expr, MetadataEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_tag_value_target_set_stamped() -> None:
    expr = _evaluator('t["name"]')
    assert isinstance(expr, TagValueEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_is_tag_target_set_stamped() -> None:
    expr = _evaluator('is_tag("name")')
    assert isinstance(expr, IsTagEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_coordinate_target_set_stamped() -> None:
    expr = _evaluator("lat()")
    assert isinstance(expr, CoordinateEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_is_closed_target_set_stamped() -> None:
    expr = _evaluator("is_closed()")
    assert isinstance(expr, IsClosedEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_length_target_set_stamped() -> None:
    expr = _evaluator("length()")
    assert isinstance(expr, LengthEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def _for_stmt2(text: str) -> ForStatement:
    """Return the second statement (index 1) as a ForStatement."""
    stmt = _transform_query(text).statements[1]
    assert isinstance(stmt, ForStatement)
    return stmt


def test_sum_expr_inner_target_set_stamped() -> None:
    # Inner evaluator of sum() is stamped with the sum's input_set
    stmt = _for_stmt2("node -> .a; for(a.sum(id())) { node; }")
    sum_expr = stmt.evaluator
    assert isinstance(sum_expr, SumEvaluator)
    assert isinstance(sum_expr.evaluator, MetadataEvaluator)
    assert sum_expr.evaluator.target_set is not None
    assert sum_expr.evaluator.target_set.name == "a"


def test_unique_expr_inner_target_set_stamped() -> None:
    stmt = _for_stmt2("node -> .a; for(a.u(id())) { node; }")
    unique_expr = stmt.evaluator
    assert isinstance(unique_expr, UniqueEvaluator)
    assert isinstance(unique_expr.evaluator, MetadataEvaluator)
    assert unique_expr.evaluator.target_set is not None
    assert unique_expr.evaluator.target_set.name == "a"


def test_min_expr_inner_target_set_stamped() -> None:
    stmt = _for_stmt2("node -> .a; for(a.min(id())) { node; }")
    min_expr = stmt.evaluator
    assert isinstance(min_expr, MinMaxEvaluator)
    assert isinstance(min_expr.evaluator, MetadataEvaluator)
    assert min_expr.evaluator.target_set is not None
    assert min_expr.evaluator.target_set.name == "a"


def test_max_expr_inner_target_set_stamped() -> None:
    stmt = _for_stmt2("node -> .a; for(a.max(id())) { node; }")
    max_expr = stmt.evaluator
    assert isinstance(max_expr, MinMaxEvaluator)
    assert isinstance(max_expr.evaluator, MetadataEvaluator)
    assert max_expr.evaluator.target_set is not None
    assert max_expr.evaluator.target_set.name == "a"


def test_aggregator_context_does_not_bleed_out() -> None:
    # Evaluators outside the aggregator boundary get the outer (for loop) context,
    # not the aggregator's input_set.
    stmt = _for_stmt2("node -> .a; for(id() + a.sum(id())) { node; }")
    add_expr = stmt.evaluator
    assert isinstance(add_expr, AddEvaluator)
    outer_id = add_expr.left_operand
    assert isinstance(outer_id, MetadataEvaluator)
    assert outer_id.target_set is not None
    assert outer_id.target_set.name == "_"
    sum_expr = add_expr.right_operand
    assert isinstance(sum_expr, SumEvaluator)
    inner_id = sum_expr.evaluator
    assert isinstance(inner_id, MetadataEvaluator)
    assert inner_id.target_set is not None
    assert inner_id.target_set.name == "a"


def test_if_filter_target_set_default_output() -> None:
    # if_filter evaluator is stamped with the query's output_set
    f = _first_filter("node(if:id());")
    assert isinstance(f, IfFilter)
    assert isinstance(f.evaluator, MetadataEvaluator)
    assert f.evaluator.target_set is not None
    assert f.evaluator.target_set.name == "_"


def test_if_filter_target_set_named_output() -> None:
    # Named output set is used, not the default
    f = _first_filter("node(if:id()) -> .a;")
    assert isinstance(f, IfFilter)
    assert isinstance(f.evaluator, MetadataEvaluator)
    assert f.evaluator.target_set is not None
    assert f.evaluator.target_set.name == "a"


def test_count_tags_target_set_stamped() -> None:
    expr = _evaluator("count_tags()")
    assert isinstance(expr, CountTagsEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_count_members_target_set_stamped() -> None:
    expr = _evaluator("count_members()")
    assert isinstance(expr, CountMembersEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_count_distinct_members_target_set_stamped() -> None:
    expr = _evaluator("count_distinct_members()")
    assert isinstance(expr, CountMembersEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_count_by_role_target_set_stamped() -> None:
    expr = _evaluator('count_by_role("outer")')
    assert isinstance(expr, CountByRoleEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"


def test_count_distinct_by_role_target_set_stamped() -> None:
    expr = _evaluator('count_distinct_by_role("outer")')
    assert isinstance(expr, CountByRoleEvaluator)
    assert expr.target_set is not None
    assert expr.target_set.name == "_"
