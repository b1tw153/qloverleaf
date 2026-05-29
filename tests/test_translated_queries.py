import pytest
import requests

from qloverleaf import interpreter
from qloverleaf.composer import compose
from qloverleaf.interpreter import SetState, SetStateEntry
from qloverleaf.parser import parse
from qloverleaf.query_context import QueryContext
from qloverleaf.transformer import ElementType, OverpassTransformer
from qloverleaf.translator import SparqlPattern, render_query, translate

pytestmark = pytest.mark.live

OVERPASS_URL = "http://localhost/api/interpreter"
QLEVER_URL = "https://qlever.dev/api/osm-planet"


def _translate(text: str) -> list[SparqlPattern]:
    query = OverpassTransformer().transform(parse(text))
    return translate(query.statements[0])


def _translate_query(text: str) -> list[SparqlPattern]:
    query = OverpassTransformer().transform(parse(text))
    return [
        pattern for statement in query.statements for pattern in translate(statement)
    ]


def _execute_overpass(statement: str) -> list[str]:
    """Execute query against Overpass and return element IDs as 'type/id' strings."""
    query = "[out:json];" + statement + "out ids;"
    response = requests.post(OVERPASS_URL, data={"data": query})
    response.raise_for_status()
    result = response.json()
    return [f"{elem['type']}/{elem['id']}" for elem in result.get("elements", [])]


def _execute_qlever(sparql: str) -> list[str]:
    """Execute SPARQL against QLever and return element IDs as 'type/id' strings."""
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    result = response.json()
    ids = []
    for binding in result.get("results", {}).get("bindings", []):
        for var_value in binding.values():
            if var_value.get("type") == "uri":
                uri = var_value["value"]
                if "/node/" in uri:
                    node_id = uri.split("/node/")[1]
                    ids.append(f"node/{node_id}")
                elif "/way/" in uri:
                    way_id = uri.split("/way/")[1]
                    ids.append(f"way/{way_id}")
                elif "/relation/" in uri:
                    rel_id = uri.split("/relation/")[1]
                    ids.append(f"relation/{rel_id}")
    return ids


# ---------------------------------------------------------------------------
# TagKeyFilter
# ---------------------------------------------------------------------------


def test_translated_tag_key_exists() -> None:
    statement = 'node["seamark:daymark:category"];'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# TagValueFilter
# ---------------------------------------------------------------------------


def test_translated_tag_value_equals() -> None:
    statement = "nwr[natural=cirque];"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# BboxFilter
# ---------------------------------------------------------------------------


def test_translated_bbox_nodes() -> None:
    statement = "node[natural=peak](32.58870,-116.14417,32.88870,-115.84417);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# IdFilter
# ---------------------------------------------------------------------------


def test_translated_id_filter() -> None:
    statement = "node(id:1,100,1000);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# AroundSetFilter
# ---------------------------------------------------------------------------


def test_translated_around_set_filter() -> None:
    # TODO: This filter and others like it cannot run without additional filters to
    # reduce the scope of element scanning in Qlever. See query-validation.md for a
    # plan to reject hazardous queries.
    query = "node(1) -> .a; node[natural=tree](around.a:100);"
    overpass_ids = _execute_overpass(query)
    patterns = _translate_query(query)
    set_state: SetState = {}
    composed = compose(patterns[0], set_state)
    assert composed is not None
    assert composed.result_set_name is not None
    set_state[composed.result_set_name] = SetStateEntry(
        pattern=composed,
        nwr_results=None,
        area_results=None,
    )
    composed = compose(patterns[1], set_state)
    assert composed is not None
    qlever_query = render_query(composed, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# AroundPointFilter
# ---------------------------------------------------------------------------


def test_translated_around_point() -> None:
    statement = "node[natural=peak](around:25000,32.73870,-115.99417);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# AroundLineFilter
# ---------------------------------------------------------------------------


def test_translated_around_line() -> None:
    statement = "node[natural=peak](around:3000,32.8253,-116.0153,32.7319,-116.0495);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# PolygonFilter
# ---------------------------------------------------------------------------


def test_translated_polygon() -> None:
    statement = (
        'node[natural=peak](poly:"32.60 -116.12 32.78 -116.10 32.85 -115.90 32.70 '
        '-115.86 32.58 -115.95");'
    )
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# NewerFilter
# ---------------------------------------------------------------------------


def test_translated_newer() -> None:
    statement = (
        'node[natural=peak](newer:"2025-01-01T00:00:00Z")(32.58870,-116.14417,'
        "32.88870,-115.84417);"
    )
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# UserFilter
# ---------------------------------------------------------------------------


def test_translated_user() -> None:
    statement = (
        'node[natural=peak](user:"Yushclay")(32.58870,-116.14417,32.88870,-115.84417);'
    )
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# UidFilter
# ---------------------------------------------------------------------------


def test_translated_uid() -> None:
    statement = (
        "node[natural=peak](uid:23131980)(32.58870,-116.14417,32.88870,-115.84417);"
    )
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# AreaIdFilter
# ---------------------------------------------------------------------------


def test_translated_area_id() -> None:
    statement = "node[geological=meteor_crater](area:3602978650);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# AreaSetFilter
# ---------------------------------------------------------------------------


def test_translated_area_set_filter() -> None:
    query = "area[name=Ocotillo] -> .a; way[highway=track](area.a);"
    overpass_ids = _execute_overpass(query)
    patterns = _translate_query(query)
    set_state: SetState = {}
    composed = compose(patterns[0], set_state)
    assert composed is not None
    assert composed.result_set_name is not None
    set_state[composed.result_set_name] = SetStateEntry(
        pattern=composed,
        nwr_results=None,
        area_results=None,
    )
    composed = compose(patterns[1], set_state)
    assert composed is not None
    qlever_query = render_query(composed, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# RecurseFilter
# ---------------------------------------------------------------------------


def _compose_two(query: str) -> tuple[str, list[str]]:
    """Translate a two-statement query and compose both patterns.

    Returns (rendered_sparql_query, overpass_ids).
    """
    overpass_ids = _execute_overpass(query)
    patterns = _translate_query(query)
    set_state: SetState = {}
    composed = compose(patterns[0], set_state)
    assert composed is not None
    assert composed.result_set_name is not None
    set_state[composed.result_set_name] = SetStateEntry(
        pattern=composed,
        nwr_results=None,
        area_results=None,
    )
    composed = compose(patterns[1], set_state)
    assert composed is not None
    return render_query(composed, set_state), overpass_ids


def _compose_chain(query: str) -> tuple[str, list[str]]:
    """Translate a query whose final statement is an explicit `out`, compose
    every pattern sequentially, and return (rendered_sparql_query, overpass_ids).
    """
    overpass_ids = _execute_overpass_with_out(query)
    patterns = _translate_query(query)
    set_state: SetState = {}
    composed = None
    for pattern in patterns:
        composed = compose(pattern, set_state)
        assert composed is not None
        if composed.result_set_name is not None:
            set_state[composed.result_set_name] = SetStateEntry(
                pattern=composed, nwr_results=None, area_results=None
            )
    assert composed is not None
    return render_query(composed, set_state), overpass_ids


def test_translated_recurse_w_filter() -> None:
    # nodes that are members of way 100 (24 nodes)
    query = "way(100) -> .a; node(w.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_r_filter() -> None:
    # way members of relation 10000, no role restriction (9 ways)
    query = "relation(10000) -> .a; way(r.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_r_filter_role() -> None:
    # way members of relation 10000 with role "outer" (1 way)
    query = 'relation(10000) -> .a; way(r.a:"outer");'
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_bw_filter() -> None:
    # parent relations of way 100 (14 relations)
    query = "way(100) -> .a; relation(bw.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_br_filter() -> None:
    # parent relations of relation 1919618 (1 relation)
    query = "relation(1919618) -> .a; relation(br.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_bn_way_untagged() -> None:
    # parent ways of node 3843108154 (untagged → http:// URI; 4 ways)
    query = "node(3843108154) -> .a; way(bn.a);"
    qlever_query, overpass_ids = _compose_two(query)
    print(qlever_query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_bn_way_by_membership() -> None:
    # parent ways of node 3843108154 (untagged → http:// URI; 4 ways)
    query = "way(381029345) -> .a; node(w.a) -> .b; way(bn.b); out ids;"
    qlever_query, overpass_ids = _compose_chain(query)
    print(qlever_query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_bn_way_tagged() -> None:
    # parent ways of node 296263439 (tagged → https:// URI; 4 ways)
    query = "node(296263439) -> .a; way(bn.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_bn_relation_untagged() -> None:
    # parent relations of node 3843108154 (untagged → http:// URI; 6 relations)
    query = "node(3843108154) -> .a; relation(bn.a);"
    qlever_query, overpass_ids = _compose_two(query)
    print(qlever_query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_recurse_bn_relation_tagged() -> None:
    # parent relations of node 296263439 (tagged → https:// URI; 1 relation)
    query = "node(296263439) -> .a; relation(bn.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# WayCountFilter
# ---------------------------------------------------------------------------


def test_translated_way_count_filter() -> None:
    # 7 highway ways sharing nodes with way 100; produces 8 junction nodes
    ways = "100,4055383,4055631,8046838,17967466,169588430,169588433"
    way_query = f"way(id:{ways}) -> .ways;"
    full_query = way_query + "node(way_cnt.ways:2-);"
    overpass_ids = _execute_overpass(full_query)

    patterns = _translate_query(full_query)
    set_state: SetState = {}

    # Execute first pattern on QLever to materialize way URIs
    composed_ways = compose(patterns[0], set_state)
    assert composed_ways is not None
    assert composed_ways.result_set_name is not None
    way_sparql = render_query(composed_ways, set_state)
    way_ids = _execute_qlever(way_sparql)
    way_uris = [
        (ElementType.WAY, f"https://www.openstreetmap.org/way/{s.split('/')[1]}")
        for s in way_ids
    ]
    set_state[composed_ways.result_set_name] = SetStateEntry(
        pattern=composed_ways,
        nwr_results=way_uris,
        area_results=None,
    )

    # Render second pattern directly — must_materialize, VALUES pre-populated
    node_sparql = render_query(patterns[1], set_state)
    qlever_ids = _execute_qlever(node_sparql)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# SetFilter
# ---------------------------------------------------------------------------


def test_translated_set_filter_node() -> None:
    # node 1 stored in .a; retrieve nodes from .a (should return node 1)
    query = "node(1) -> .a; node.a[man_made=mast];"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_set_filter_way() -> None:
    # way 100 stored in .a; retrieve ways from .a (should return way 100)
    query = "way(100) -> .a; way.a[highway=secondary];"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_set_filter_relation() -> None:
    # relation 10000 stored in .a; retrieve relations from .a
    # (should return relation 10000)
    query = "relation(10000) -> .a; relation.a[water=lake];"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_set_filter_nwr() -> None:
    query = "nwr[natural=sinkhole] -> .a; nwr.a[sinkhole=bluehole];"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# ItemStatement
# ---------------------------------------------------------------------------


def test_translated_item_to_default_set() -> None:
    # .a; copies .a into ._; the composer inlines .a's cold pattern into ._
    query = "node(1) -> .a; .a;"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_item_redirect() -> None:
    # .a -> .b; copies .a into .b; a downstream set filter resolves through both hops
    query = "node(1) -> .a; .a -> .b; node.b;"
    overpass_ids = _execute_overpass(query)
    patterns = _translate_query(query)
    set_state: SetState = {}
    for pattern in patterns[:2]:
        composed = compose(pattern, set_state)
        assert composed is not None
        assert composed.result_set_name is not None
        set_state[composed.result_set_name] = SetStateEntry(
            pattern=composed, nwr_results=None, area_results=None
        )
    composed = compose(patterns[2], set_state)
    assert composed is not None
    qlever_query = render_query(composed, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# PivotFilter
# ---------------------------------------------------------------------------


def test_translated_pivot_filter_way() -> None:
    query = "area[name=Ocotillo] -> .a; way(pivot.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_pivot_filter_relation() -> None:
    query = "area[name='El Centro'] -> .a; relation(pivot.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_pivot_filter_wr() -> None:
    query = "area[name='El Centro'] -> .a; wr(pivot.a);"
    qlever_query, overpass_ids = _compose_two(query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# IfFilter
# ---------------------------------------------------------------------------


def test_translated_if_filter_truthy_literal() -> None:
    # if:1 is always true; result should match the unfiltered node(1)
    statement = "node(1)(if:1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    print(qlever_query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_filter_falsy_literal() -> None:
    # if:0 is always false; both backends should return no elements
    statement = "node(1)(if:0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    print(qlever_query)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# CompareEvaluator


def test_translated_if_compare_equal() -> None:
    statement = "node(1)(if:1==1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_not_equal() -> None:
    statement = "node(1)(if:1!=0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_less_than() -> None:
    statement = "node(1)(if:0<1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_less_than_or_equal() -> None:
    statement = "node(1)(if:1<=1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_greater_than() -> None:
    statement = "node(1)(if:1>0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_greater_than_or_equal() -> None:
    statement = "node(1)(if:1>=1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# CompareEvaluator — type mismatches
#
# Overpass comparison coercion: int64 → double → lexicographic string fallback.
# SPARQL raises a type error for all comparisons between incompatible types;
# FILTER treats type errors as false.
#
# == agrees: Overpass string-compares "1" vs "hello" → not equal; SPARQL also
# returns not-equal (different RDF terms). Both false.
#
# != diverges: Overpass string-compares → not equal → true; QLever raises a type
# error → false. xfail tests document this divergence.
#
# Ordering: SPARQL always returns false (type error). Overpass falls back to
# lexicographic string comparison. "h" > "1" (ASCII 104 > 49), so the direction
# matters: "hello" < 1 and 1 > "hello" produce false on both backends (agree),
# while 1 < "hello" and "hello" > 1 produce true in Overpass but false in QLever
# (diverge). xfail tests cover the diverging directions for all four operators.


def test_translated_if_compare_type_mismatch_equal() -> None:
    # int vs non-numeric string: Overpass string-compares "1" vs "hello" → not equal.
    # SPARQL: different RDF terms → not equal. Both return false.
    statement = 'node(1)(if:1=="hello");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="QLever type error on != with incompatible types → false; "
    "Overpass string fallback → true"
)
def test_translated_if_compare_type_mismatch_not_equal() -> None:
    # int vs non-numeric string: Overpass string-compares "1" vs "hello" → not equal →
    # true. QLever raises a type error → filter false. Backends diverge.
    statement = 'node(1)(if:1!="hello");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_type_mismatch_less_than_agree() -> None:
    # "hello" < 1: Overpass string-compares "hello" vs "1" → "h" > "1" → false.
    # SPARQL: type error → filter false. Both return false.
    statement = 'node(1)(if:"hello"<1);'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="QLever type error on < with incompatible types → false; "
    "Overpass string fallback: '1' < 'h' → true"
)
def test_translated_if_compare_type_mismatch_less_than_diverge() -> None:
    # 1 < "hello": Overpass string-compares "1" vs "hello" → "1" < "h" → true.
    # QLever: type error → filter false. Backends diverge.
    statement = 'node(1)(if:1<"hello");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_type_mismatch_greater_than_agree() -> None:
    # 1 > "hello": Overpass string-compares "1" vs "hello" → "1" < "h" → false.
    # SPARQL: type error → filter false. Both return false.
    statement = 'node(1)(if:1>"hello");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="QLever type error on > with incompatible types → false; "
    "Overpass string fallback: 'h' > '1' → true"
)
def test_translated_if_compare_type_mismatch_greater_than_diverge() -> None:
    # "hello" > 1: Overpass string-compares "hello" vs "1" → "h" > "1" → true.
    # QLever: type error → filter false. Backends diverge.
    statement = 'node(1)(if:"hello">1);'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_type_mismatch_less_than_or_equal_agree() -> None:
    # "hello" <= 1: Overpass string-compares "hello" vs "1" → "h" > "1" → false.
    # SPARQL: type error → filter false. Both return false.
    statement = 'node(1)(if:"hello"<=1);'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="QLever type error on <= with incompatible types → false; "
    "Overpass string fallback: '1' <= 'h' → true"
)
def test_translated_if_compare_type_mismatch_less_than_or_equal_diverge() -> None:
    # 1 <= "hello": Overpass string-compares "1" vs "hello" → "1" <= "h" → true.
    # QLever: type error → filter false. Backends diverge.
    statement = 'node(1)(if:1<="hello");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_compare_type_mismatch_greater_than_or_equal_agree() -> None:
    # 1 >= "hello": Overpass string-compares "1" vs "hello" → "1" < "h" → false.
    # SPARQL: type error → filter false. Both return false.
    statement = 'node(1)(if:1>="hello");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="QLever type error on >= with incompatible types → false; "
    "Overpass string fallback: 'h' >= '1' → true"
)
def test_translated_if_compare_type_mismatch_greater_than_or_equal_diverge() -> None:
    # "hello" >= 1: Overpass string-compares "hello" vs "1" → "h" >= "1" → true.
    # QLever: type error → filter false. Backends diverge.
    statement = 'node(1)(if:"hello">=1);'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# UnaryEvaluator


def test_translated_if_not_falsy() -> None:
    # !0: 0 is falsy, NOT → true
    statement = "node(1)(if:!0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_not_truthy() -> None:
    # !1: 1 is truthy, NOT → false
    statement = "node(1)(if:!1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_negate() -> None:
    # -1 < 0: negation produces a negative number
    statement = "node(1)(if:-1<0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="Overpass: -'foo' → 'NaN', which is truthy (NaN != 0); "
    "QLever: type error on -('foo') → filter false"
)
def test_translated_if_negate_type_mismatch() -> None:
    # Negating a non-numeric string: Overpass produces "NaN" (truthy); QLever errors.
    statement = 'node(1)(if:-"foo");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# BinaryEvaluator
#
# && and || use the same boolean EBV rules as !. SPARQL's EBV for non-numeric
# plain literals (empty = false, non-empty = true) aligns with Overpass's
# string_represents_boolean_true, so there are no diverging cases to document.


def test_translated_if_and_truthy() -> None:
    statement = "node(1)(if:1&&1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_and_falsy() -> None:
    statement = "node(1)(if:1&&0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_or_truthy() -> None:
    statement = "node(1)(if:0||1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_or_falsy() -> None:
    statement = "node(1)(if:0||0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# TernaryEvaluator


def test_translated_if_ternary_true_branch() -> None:
    # 1?1:0 → condition true → result 1 → truthy
    statement = "node(1)(if:1?1:0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_ternary_false_branch() -> None:
    # 0?1:0 → condition false → result 0 → falsy
    statement = "node(1)(if:0?1:0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# AddEvaluator
#
# Three translation paths:
#   both numeric → (l) + (r) or (l) - (r)
#   ADD, at least one LITERAL → CONCAT(str(l), str(r))
#   SUB with non-numeric operand → output_type=None, arithmetic syntax with a warning
#
# The subtraction mismatch diverges: Overpass produces "NaN" (truthy), while
# QLever raises a type error (filter false). xfail test documents this divergence.


def test_translated_if_add_numeric() -> None:
    # 1+1 → 2 → truthy
    statement = "node(1)(if:1+1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_add_concat() -> None:
    # "foo"+"bar" → "foobar" → truthy; translates to CONCAT
    statement = 'node(1)(if:"foo"+"bar");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_subtract_truthy() -> None:
    # 2-1 → 1 → truthy
    statement = "node(1)(if:2-1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_subtract_falsy() -> None:
    # 1-1 → 0 → falsy
    statement = "node(1)(if:1-1);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_add_type_mismatch() -> None:
    # string + int: Overpass concatenates → "foo1" (truthy).
    # Translated as CONCAT(str("foo"), str(1)) → "foo1" (truthy). Both agree.
    statement = 'node(1)(if:"foo"+1);'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="Overpass: 'foo'-1 → 'NaN' (truthy, NaN != 0); "
    "QLever: type error on ('foo') - (1) → filter false"
)
def test_translated_if_subtract_type_mismatch() -> None:
    # string - int: Overpass produces "NaN" (truthy); QLever type error → false
    statement = 'node(1)(if:"foo"-1);'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# MultiplyEvaluator
#
# Both numeric → (l) * (r) or (l) / (r).
# Mixed types → output_type=None, arithmetic syntax with a warning.
# Diverges: Overpass produces "NaN" (truthy); QLever type error → filter false.


def test_translated_if_multiply_truthy() -> None:
    # 2*3 → 6 → truthy
    statement = "node(1)(if:2*3);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_multiply_falsy() -> None:
    # 0*5 → 0 → falsy
    statement = "node(1)(if:0*5);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_divide_truthy() -> None:
    # 6/2 → 3 → truthy
    statement = "node(1)(if:6/2);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_divide_falsy() -> None:
    # 0/5 → 0 → falsy
    statement = "node(1)(if:0/5);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="Overpass: 'foo'*2 → 'NaN' (truthy, NaN != 0); "
    "QLever: type error on ('foo') * (2) → filter false"
)
def test_translated_if_multiply_type_mismatch() -> None:
    # string * int: Overpass produces "NaN" (truthy); QLever type error → false
    statement = 'node(1)(if:"foo"*2);'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="Overpass: 'foo'/2 → 'NaN' (truthy, NaN != 0); "
    "QLever: type error on ('foo') / (2) → filter false"
)
def test_translated_if_divide_type_mismatch() -> None:
    # string / int: Overpass produces "NaN" (truthy); QLever type error → false
    statement = 'node(1)(if:"foo"/2);'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# AbsEvaluator


def test_translated_if_abs_truthy() -> None:
    # abs(-1) → 1 → truthy
    statement = "node(1)(if:abs(-1));"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_abs_falsy() -> None:
    # abs(0) → 0 → falsy
    statement = "node(1)(if:abs(0));"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="Overpass: abs('foo') → 'NaN' (truthy, NaN != 0); "
    "QLever: type error on ABS('foo') → filter false"
)
def test_translated_if_abs_type_mismatch() -> None:
    # abs on a non-numeric string: Overpass produces "NaN" (truthy); QLever errors
    statement = 'node(1)(if:abs("foo"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# TypeCheckEvaluator (is_number, is_date)


def test_translated_if_is_number_truthy() -> None:
    # is_number("42") → 1 → truthy
    statement = 'node(1)(if:is_number("42"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_number_falsy() -> None:
    # is_number("foo") → 0 → falsy
    statement = 'node(1)(if:is_number("foo"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_number_leading_plus() -> None:
    statement = 'node(1)(if:is_number("+1"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_number_trailing_decimal() -> None:
    # "1." → DECIMAL (typed numeric) → is_number always true
    statement = "node(1)(if:is_number(1.));"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_number_leading_decimal() -> None:
    # ".5" → DECIMAL (typed numeric) → is_number always true
    statement = 'node(1)(if:is_number(".5"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_number_scientific_notation() -> None:
    # "1.2e1" → DOUBLE (typed numeric) → is_number always true
    statement = "node(1)(if:is_number(1.2e1));"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_date_truthy() -> None:
    # is_date("2024-01-01") → 1 → truthy
    statement = 'node(1)(if:is_date("2024-01-01"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_date_with_time_truthy() -> None:
    # is_date("2024-01-01T12:00:00Z") → 1 → truthy
    statement = 'node(1)(if:is_date("2024-01-01T12:00:00Z"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_date_falsy() -> None:
    # is_date("foo") → 0 → falsy
    statement = 'node(1)(if:is_date("foo"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_date_timezone_offset() -> None:
    # datetime.fromisoformat() accepts timezone offset forms, so _infer_literal_type
    # classifies "2024-01-01T12:00:00+01:00" as DATETIME → short-circuit to true
    statement = 'node(1)(if:is_date("2024-01-01T12:00:00+01:00"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ConversionEvaluator (number, date)


def test_translated_if_number_truthy() -> None:
    # number("42") → 42.0 → truthy
    statement = 'node(1)(if:number("42"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_number_falsy() -> None:
    # number("0") → 0.0 → falsy
    statement = 'node(1)(if:number("0"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


@pytest.mark.xfail(
    reason="Overpass: number('foo') → NaN (truthy, NaN != 0); "
    "QLever: xsd:double cast error → filter false"
)
def test_translated_if_number_invalid() -> None:
    # invalid string: Overpass produces NaN (truthy); QLever cast error → false
    statement = 'node(1)(if:number("foo"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_date_comparison_earlier() -> None:
    # date("2024-01-01") < date("2024-12-31") → true → truthy
    statement = 'node(1)(if:date("2024-01-01") < date("2024-12-31"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_date_comparison_later() -> None:
    # date("2024-12-31") < date("2024-01-01") → false → falsy
    statement = 'node(1)(if:date("2024-12-31") < date("2024-01-01"));'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# SuffixEvaluator


def test_translated_if_suffix_with_prefix() -> None:
    # suffix("123m") strips the numeric prefix → "m"; "m" != "" → truthy
    statement = 'node(1)(if:suffix("123m") == "m");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_suffix_all_numeric() -> None:
    # suffix("123") → "" (all digits stripped); "" == "" → truthy
    statement = 'node(1)(if:suffix("123") == "");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_suffix_no_numeric_prefix() -> None:
    # no numeric prefix: Overpass returns ""; QLever leaves the string unchanged
    statement = 'node(1)(if:suffix("foo") == "");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_suffix_whitespace() -> None:
    # whitespace between number and unit: Overpass strips it, QLever preserves it
    statement = 'node(1)(if:suffix("734 m") == "m");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_suffix_whitespace_minus_prefix() -> None:
    # whitespace between number and unit: Overpass strips it, QLever preserves it
    statement = 'node(1)(if:suffix("-734 m") == "m");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_suffix_whitespace_plus_prefix() -> None:
    # whitespace between number and unit: Overpass strips it, QLever preserves it
    statement = 'node(1)(if:suffix("+734 m") == "m");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# TagValueEvaluator


@pytest.mark.xfail(
    reason='Overpass: t["ele"] returns a string, implicitly converted to a number; '
    'QLever: t["ele"] returns literal, literal > xsd:int → type mismatch → '
    "comparison fails"
)
def test_translated_if_tag_value_numeric_compare() -> None:
    # number() converts the tag string to a numeric type for comparison
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f'node[natural=peak](if:t["ele"]>700){bbox};'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_tag_value_numeric_compare_with_conversion() -> None:
    # number() converts the tag string to a numeric type for comparison
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f'node[natural=peak](if:number(t["ele"])>700){bbox};'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_tag_value_string_compare() -> None:
    # tag equality via t[...] — equivalent to the tag filter form [key=value]
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f'node[natural=peak](if:t["natural"]=="peak"){bbox};'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_tag_value_missing() -> None:
    # t["ele"] on a node without the tag returns "" in Overpass; COALESCE matches
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f'node[natural=peak](if:t["ele"]==""){bbox};'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# IsTagEvaluator


def test_translated_if_is_tag_present() -> None:
    # is_tag returns true when the tag exists; OPTIONAL binds → BOUND is true
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f'node[natural=peak](if:is_tag("ele")){bbox};'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_tag_absent() -> None:
    # is_tag returns false when the tag is missing; OPTIONAL does not bind
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f'node[natural=peak](if:is_tag("nonexistent_tag_xyz")){bbox};'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# MetadataEvaluator


def test_translated_if_id_compare() -> None:
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"node[natural=peak](if:id()>1){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_type_compare() -> None:
    # type() returns "node", "way", or "relation"
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f'nwr[natural=peak](if:type()=="node"){bbox};'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_version_compare() -> None:
    # version() is typed xsd:int in QLever; direct numeric comparison works
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"node[natural=peak](if:version()>3){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_timestamp_compare() -> None:
    # timestamp() is xsd:dateTime in QLever; date() converts the string for comparison
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    cutoff = "2020-01-01T00:00:00Z"
    statement = f'node[natural=peak](if:timestamp()>date("{cutoff}")){bbox};'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_uid_compare() -> None:
    # uid() is typed xsd:int in QLever; direct numeric comparison works
    statement = "node(1)(if:uid()>0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_user_compare() -> None:
    # user() is a plain literal in QLever; string comparison works directly
    statement = 'node(1)(if:user()!="");'
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_changeset_compare() -> None:
    statement = "node(1)(if:changeset()>0);"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# CoordinateEvaluator


def test_translated_if_lat_truthy() -> None:
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"node[natural=peak](if:lat()>32.7){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_lat_falsy() -> None:
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"node[natural=peak](if:lat()>90){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_lon_truthy() -> None:
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"node[natural=peak](if:lon()>-116){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_lon_falsy() -> None:
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"node[natural=peak](if:lon()>0){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# LengthEvaluator


def test_translated_if_length_truthy() -> None:
    # osm2rdf:length is precomputed for ways; direct decimal comparison
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"way[highway=secondary](if:length()>500){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_length_node_absent() -> None:
    # nodes have no osm2rdf:length; COALESCE returns 0, matching Overpass
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"node[natural=peak](if:length()>0){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# IsClosedEvaluator


def test_translated_if_is_closed_closed_way() -> None:
    # building ways are always closed, but only some ruins are; osm2rdf:area is present
    # The bbox filter does not limit the scope of the result scan in QLever. This is a
    # known limitation. And (if:is_closed()) is a FILTER clause on query results. The
    # remaining query, must produce a small result set or the query will time out.
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"way['ruins:building'=yes](if:is_closed()){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_if_is_closed_open_way() -> None:
    # building ways are always closed, some ruins are not; osm2rdf:area is absent
    # The bbox filter does not limit the scope of the result scan in QLever. This is a
    # known limitation. And (if:is_closed()) is a FILTER clause on query results. The
    # remaining query, must produce a small result set or the query will time out.
    bbox = "(32.58870,-116.14417,32.88870,-115.84417)"
    statement = f"way['ruins:building'=yes](if:!is_closed()){bbox};"
    pattern = _translate(statement)[0]
    overpass_ids = _execute_overpass(statement)
    set_state: SetState = {}
    qlever_query = render_query(pattern, set_state)
    qlever_ids = _execute_qlever(qlever_query)
    assert sorted(overpass_ids) == sorted(qlever_ids)


# ---------------------------------------------------------------------------
# out sort and limit
# ---------------------------------------------------------------------------


def _execute_overpass_with_out(query: str) -> list[str]:
    """Execute a complete Overpass query that already includes an out statement."""
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    return [f"{e['type']}/{e['id']}" for e in response.json().get("elements", [])]


def _compose_out_query(query: str) -> str:
    """Translate a query+out statement pair and return rendered SPARQL."""
    patterns = _translate_query(query)
    set_state: SetState = {}
    composed = compose(patterns[0], set_state)
    assert composed is not None
    assert composed.result_set_name is not None
    set_state[composed.result_set_name] = SetStateEntry(
        pattern=composed, nwr_results=None, area_results=None
    )
    composed = compose(patterns[1], set_state)
    assert composed is not None
    return render_query(composed, set_state)


def test_translated_out_sort_asc() -> None:
    # asc sort: results must be in ascending ID order on both backends
    query = "node(id:1,2,3); out ids asc;"
    overpass_ids = _execute_overpass_with_out(query)
    qlever_ids = _execute_qlever(_compose_out_query(query))
    assert overpass_ids == qlever_ids


def test_translated_out_limit() -> None:
    # limit 2: both backends return the first 2 elements (by ascending ID)
    query = "node(id:1,2,3); out ids 2;"
    overpass_ids = _execute_overpass_with_out(query)
    qlever_ids = _execute_qlever(_compose_out_query(query))
    assert sorted(overpass_ids) == sorted(qlever_ids)


def test_translated_out_limit_zero() -> None:
    # limit 0: both backends return no elements
    query = "node(id:1,2,3); out ids 0;"
    overpass_ids = _execute_overpass_with_out(query)
    qlever_ids = _execute_qlever(_compose_out_query(query))
    assert overpass_ids == qlever_ids == []


# ---------------------------------------------------------------------------
# out center
# ---------------------------------------------------------------------------


def _parse_wkt_point(wkt: str) -> tuple[float, float]:
    """Parse WKT POINT(lon lat) and return (lat, lon)."""
    coords = wkt.strip().removeprefix("POINT(").removesuffix(")")
    lon_str, lat_str = coords.split()
    return float(lat_str), float(lon_str)


def _overpass_center_coords(query: str) -> dict[str, tuple[float, float]]:
    """Execute Overpass and return {type/id: (lat, lon)} from center or lat/lon."""
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    result = {}
    for elem in response.json().get("elements", []):
        eid = f"{elem['type']}/{elem['id']}"
        if "center" in elem:
            result[eid] = (elem["center"]["lat"], elem["center"]["lon"])
        elif "lat" in elem:
            result[eid] = (elem["lat"], elem["lon"])
    return result


def _qlever_centroid_coords(sparql: str) -> dict[str, tuple[float, float]]:
    """Execute SPARQL and return {type/id: (lat, lon)} from ?centroid WKT bindings."""
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    result = {}
    for binding in response.json().get("results", {}).get("bindings", []):
        eid = None
        latlon = None
        for var_value in binding.values():
            if var_value.get("type") == "uri":
                uri = var_value["value"]
                for path in ("/node/", "/way/", "/relation/"):
                    if path in uri:
                        eid = f"{path.strip('/')}/{uri.split(path)[1]}"
                        break
            elif var_value.get("type") == "literal":
                val = var_value.get("value", "")
                if val.startswith("POINT("):
                    latlon = _parse_wkt_point(val)
        if eid and latlon:
            result[eid] = latlon
    return result


def _assert_center_coords(
    overpass_data: dict[str, tuple[float, float]],
    qlever_data: dict[str, tuple[float, float]],
) -> None:
    assert set(overpass_data) == set(qlever_data)
    for eid in overpass_data:
        op_lat, op_lon = overpass_data[eid]
        ql_lat, ql_lon = qlever_data[eid]
        assert op_lat == pytest.approx(ql_lat, abs=0.01), f"{eid} lat mismatch"
        assert op_lon == pytest.approx(ql_lon, abs=0.01), f"{eid} lon mismatch"


def test_translated_out_center_nodes() -> None:
    # nodes: Overpass returns lat/lon inline (no center object); QLever uses centroid
    query = "node(id:1,2,3); out ids center;"
    _assert_center_coords(
        _overpass_center_coords(query),
        _qlever_centroid_coords(_compose_out_query(query)),
    )


def test_translated_out_center_ways() -> None:
    # ways: Overpass returns center.lat/lon; QLever computes geof:centroid from geometry
    query = "way(id:44019040,992347334,1122162378); out ids center;"
    _assert_center_coords(
        _overpass_center_coords(query),
        _qlever_centroid_coords(_compose_out_query(query)),
    )


def test_translated_out_center_relations() -> None:
    # relations: Overpass returns center.lat/lon; QLever computes geof:centroid
    query = "relation(id:15006797,4050577,4050578); out ids center;"
    _assert_center_coords(
        _overpass_center_coords(query),
        _qlever_centroid_coords(_compose_out_query(query)),
    )


# ---------------------------------------------------------------------------
# out skel
# ---------------------------------------------------------------------------


def _uri_to_type_id(uri: str) -> str | None:
    """Convert an OSM URI (http or https scheme) to 'type/id'."""
    for path in ("/node/", "/way/", "/relation/"):
        if path in uri:
            return f"{path.strip('/')}/{uri.split(path)[1]}"
    return None


def _overpass_skel(
    query: str,
) -> tuple[dict[str, list[tuple[int, str, str]]], dict[str, tuple[float, float]]]:
    """Execute Overpass out skel and return (member_data, node_coords).

    member_data: {element_key: [(pos, member_key, role)]}
    node_coords: {node_key: (lat, lon)}
    """
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    members: dict[str, list[tuple[int, str, str]]] = {}
    coords: dict[str, tuple[float, float]] = {}
    for elem in response.json().get("elements", []):
        eid = f"{elem['type']}/{elem['id']}"
        if elem["type"] == "node":
            members[eid] = []
            coords[eid] = (elem["lat"], elem["lon"])
        elif elem["type"] == "way":
            members[eid] = [
                (i, f"node/{nid}", "") for i, nid in enumerate(elem.get("nodes", []))
            ]
        elif elem["type"] == "relation":
            members[eid] = [
                (i, f"{m['type']}/{m['ref']}", m.get("role", ""))
                for i, m in enumerate(elem.get("members", []))
            ]
    return members, coords


def _qlever_skel(
    sparql: str,
) -> tuple[dict[str, list[tuple[int, str, str]]], dict[str, tuple[float, float]]]:
    """Execute SPARQL out skel query and return (member_data, node_coords).

    member_data: {element_key: [(pos, member_key, role)]}
    node_coords: {node_key: (lat, lon)} parsed from ?wkt POINT bindings
    """
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    data = response.json()
    elem_var = data.get("head", {}).get("vars", [""])[0]

    members: dict[str, list[tuple[int, str, str]]] = {}
    coords: dict[str, tuple[float, float]] = {}
    for binding in data.get("results", {}).get("bindings", []):
        elem_val = binding.get(elem_var, {})
        if elem_val.get("type") != "uri":
            continue
        elem_key = _uri_to_type_id(elem_val["value"])
        if elem_key is None:
            continue
        if elem_key not in members:
            members[elem_key] = []

        wkt_val = binding.get("wkt")
        if wkt_val and wkt_val.get("type") == "literal":
            wkt_str = wkt_val["value"]
            if wkt_str.startswith("POINT("):
                coords[elem_key] = _parse_wkt_point(wkt_str)

        member_val = binding.get("member")
        pos_val = binding.get("pos")
        if member_val and member_val.get("type") == "uri" and pos_val:
            member_key = _uri_to_type_id(member_val["value"])
            if member_key:
                pos = int(pos_val["value"])
                role = binding.get("role", {}).get("value", "")
                members[elem_key].append((pos, member_key, role))

    for elem_members in members.values():
        elem_members.sort()

    return members, coords


def _assert_node_coords(
    overpass_data: dict[str, tuple[float, float]],
    qlever_data: dict[str, tuple[float, float]],
) -> None:
    assert set(overpass_data) == set(qlever_data)
    for eid in overpass_data:
        op_lat, op_lon = overpass_data[eid]
        ql_lat, ql_lon = qlever_data[eid]
        assert op_lat == pytest.approx(ql_lat, abs=1e-6), f"{eid} lat mismatch"
        assert op_lon == pytest.approx(ql_lon, abs=1e-6), f"{eid} lon mismatch"


def test_translated_out_skel_nodes() -> None:
    # nodes: one geometry row per node; no member data
    query = "node[name=Ocotillo]; out skel;"
    op_members, op_coords = _overpass_skel(query)
    ql_members, ql_coords = _qlever_skel(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    _assert_node_coords(op_coords, ql_coords)


def test_translated_out_skel_ways() -> None:
    # ways: ordered member node list per way
    query = "way[name=Ocotillo]; out skel;"
    op_members, _ = _overpass_skel(query)
    ql_members, _ = _qlever_skel(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]


def test_translated_out_skel_relations() -> None:
    # relations: ordered member list with roles per relation
    query = "relation[name=Ocotillo]; out skel;"
    op_members, _ = _overpass_skel(query)
    ql_members, _ = _qlever_skel(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]


def test_translated_out_skel_nwr() -> None:
    # mixed nwr: all three UNION branches active
    query = "nwr[name=Ocotillo]; out skel;"
    op_members, op_coords = _overpass_skel(query)
    ql_members, ql_coords = _qlever_skel(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    _assert_node_coords(op_coords, ql_coords)


# ---------------------------------------------------------------------------
# out tags
# ---------------------------------------------------------------------------


def _overpass_tags(query: str) -> dict[str, dict[str, str]]:
    """Execute Overpass out tags and return {element_key: {tag_key: tag_value}}."""
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    result: dict[str, dict[str, str]] = {}
    for elem in response.json().get("elements", []):
        eid = f"{elem['type']}/{elem['id']}"
        result[eid] = elem.get("tags", {})
    return result


def _qlever_tags(sparql: str) -> dict[str, dict[str, str]]:
    """Execute SPARQL out tags query and return {element_key: {tag_key: tag_value}}."""
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    data = response.json()
    elem_var = data.get("head", {}).get("vars", [""])[0]

    result: dict[str, dict[str, str]] = {}
    for binding in data.get("results", {}).get("bindings", []):
        elem_val = binding.get(elem_var, {})
        if elem_val.get("type") != "uri":
            continue
        elem_key = _uri_to_type_id(elem_val["value"])
        if elem_key is None:
            continue
        if elem_key not in result:
            result[elem_key] = {}

        pred_val = binding.get("p", {})
        val_val = binding.get("v", {})
        if pred_val.get("type") == "uri" and val_val.get("type") == "literal":
            pred_uri = pred_val["value"]
            if "Key:" in pred_uri:
                key = pred_uri.split("Key:")[1]
                result[elem_key][key] = val_val["value"]

    return result


def test_translated_out_tags_nodes() -> None:
    query = "node[name=Ocotillo]; out tags;"
    assert _overpass_tags(query) == _qlever_tags(_compose_out_query(query))


def test_translated_out_tags_ways() -> None:
    query = "way[name=Ocotillo]; out tags;"
    assert _overpass_tags(query) == _qlever_tags(_compose_out_query(query))


def test_translated_out_tags_relations() -> None:
    query = "relation[name=Ocotillo]; out tags;"
    assert _overpass_tags(query) == _qlever_tags(_compose_out_query(query))


def test_translated_out_tags_nwr() -> None:
    query = "nwr[name=Ocotillo]; out tags;"
    assert _overpass_tags(query) == _qlever_tags(_compose_out_query(query))


# ---------------------------------------------------------------------------
# out body
# ---------------------------------------------------------------------------

_SkelData = tuple[
    dict[str, list[tuple[int, str, str]]],
    dict[str, tuple[float, float]],
    dict[str, dict[str, str]],
]


def _overpass_body(query: str) -> _SkelData:
    """Execute Overpass out body and return (member_data, node_coords, tags)."""
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    members: dict[str, list[tuple[int, str, str]]] = {}
    coords: dict[str, tuple[float, float]] = {}
    tags: dict[str, dict[str, str]] = {}
    for elem in response.json().get("elements", []):
        eid = f"{elem['type']}/{elem['id']}"
        if elem["type"] == "node":
            members[eid] = []
            coords[eid] = (elem["lat"], elem["lon"])
        elif elem["type"] == "way":
            members[eid] = [
                (i, f"node/{nid}", "") for i, nid in enumerate(elem.get("nodes", []))
            ]
        elif elem["type"] == "relation":
            members[eid] = [
                (i, f"{m['type']}/{m['ref']}", m.get("role", ""))
                for i, m in enumerate(elem.get("members", []))
            ]
        tags[eid] = elem.get("tags", {})
    return members, coords, tags


def _qlever_body(sparql: str) -> _SkelData:
    """Execute SPARQL out body query and return (member_data, node_coords, tags)."""
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    data = response.json()
    elem_var = data.get("head", {}).get("vars", [""])[0]

    members: dict[str, list[tuple[int, str, str]]] = {}
    coords: dict[str, tuple[float, float]] = {}
    tags: dict[str, dict[str, str]] = {}
    for binding in data.get("results", {}).get("bindings", []):
        elem_val = binding.get(elem_var, {})
        if elem_val.get("type") != "uri":
            continue
        elem_key = _uri_to_type_id(elem_val["value"])
        if elem_key is None:
            continue
        if elem_key not in members:
            members[elem_key] = []
        if elem_key not in tags:
            tags[elem_key] = {}

        wkt_val = binding.get("wkt")
        if wkt_val and wkt_val.get("type") == "literal":
            wkt_str = wkt_val["value"]
            if wkt_str.startswith("POINT("):
                coords[elem_key] = _parse_wkt_point(wkt_str)

        member_val = binding.get("member")
        pos_val = binding.get("pos")
        if member_val and member_val.get("type") == "uri" and pos_val:
            member_key = _uri_to_type_id(member_val["value"])
            if member_key:
                pos = int(pos_val["value"])
                role = binding.get("role", {}).get("value", "")
                members[elem_key].append((pos, member_key, role))

        pred_val = binding.get("p", {})
        val_val = binding.get("v", {})
        if pred_val.get("type") == "uri" and val_val.get("type") == "literal":
            pred_uri = pred_val["value"]
            if "Key:" in pred_uri:
                tags[elem_key][pred_uri.split("Key:")[1]] = val_val["value"]

    for elem_members in members.values():
        elem_members.sort()

    return members, coords, tags


def test_translated_out_body_nodes() -> None:
    query = "node[name=Ocotillo]; out body;"
    op_members, op_coords, op_tags = _overpass_body(query)
    ql_members, ql_coords, ql_tags = _qlever_body(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    _assert_node_coords(op_coords, ql_coords)
    assert op_tags == ql_tags


def test_translated_out_body_ways() -> None:
    query = "way[name=Ocotillo]; out body;"
    op_members, _, op_tags = _overpass_body(query)
    ql_members, _, ql_tags = _qlever_body(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags


def test_translated_out_body_relations() -> None:
    query = "relation[name=Ocotillo]; out body;"
    op_members, _, op_tags = _overpass_body(query)
    ql_members, _, ql_tags = _qlever_body(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags


def test_translated_out_body_nwr() -> None:
    query = "nwr[name=Ocotillo]; out body;"
    op_members, op_coords, op_tags = _overpass_body(query)
    ql_members, ql_coords, ql_tags = _qlever_body(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    _assert_node_coords(op_coords, ql_coords)
    assert op_tags == ql_tags


# ---------------------------------------------------------------------------
# out meta
# ---------------------------------------------------------------------------

_MetaData = tuple[
    dict[str, list[tuple[int, str, str]]],
    dict[str, tuple[float, float]],
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
]

_META_FIELDS = ("version", "timestamp", "changeset", "uid", "user")


def _overpass_meta(query: str) -> _MetaData:
    """Execute Overpass out meta and return (member_data, node_coords, tags, meta)."""
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    members: dict[str, list[tuple[int, str, str]]] = {}
    coords: dict[str, tuple[float, float]] = {}
    tags: dict[str, dict[str, str]] = {}
    meta: dict[str, dict[str, str]] = {}
    for elem in response.json().get("elements", []):
        eid = f"{elem['type']}/{elem['id']}"
        if elem["type"] == "node":
            members[eid] = []
            coords[eid] = (elem["lat"], elem["lon"])
        elif elem["type"] == "way":
            members[eid] = [
                (i, f"node/{nid}", "") for i, nid in enumerate(elem.get("nodes", []))
            ]
        elif elem["type"] == "relation":
            members[eid] = [
                (i, f"{m['type']}/{m['ref']}", m.get("role", ""))
                for i, m in enumerate(elem.get("members", []))
            ]
        tags[eid] = elem.get("tags", {})
        meta[eid] = {
            "version": str(elem["version"]),
            "timestamp": elem["timestamp"].rstrip("Z"),
            "changeset": str(elem["changeset"]),
            "uid": str(elem["uid"]),
            "user": elem["user"],
        }
    return members, coords, tags, meta


def _qlever_meta(sparql: str) -> _MetaData:
    """Execute SPARQL out meta query and return
    (member_data, node_coords, tags, meta)."""
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    data = response.json()
    elem_var = data.get("head", {}).get("vars", [""])[0]

    members: dict[str, list[tuple[int, str, str]]] = {}
    coords: dict[str, tuple[float, float]] = {}
    tags: dict[str, dict[str, str]] = {}
    meta: dict[str, dict[str, str]] = {}
    for binding in data.get("results", {}).get("bindings", []):
        elem_val = binding.get(elem_var, {})
        if elem_val.get("type") != "uri":
            continue
        elem_key = _uri_to_type_id(elem_val["value"])
        if elem_key is None:
            continue
        if elem_key not in members:
            members[elem_key] = []
        if elem_key not in tags:
            tags[elem_key] = {}

        wkt_val = binding.get("wkt")
        if wkt_val and wkt_val.get("type") == "literal":
            wkt_str = wkt_val["value"]
            if wkt_str.startswith("POINT("):
                coords[elem_key] = _parse_wkt_point(wkt_str)

        member_val = binding.get("member")
        pos_val = binding.get("pos")
        if member_val and member_val.get("type") == "uri" and pos_val:
            member_key = _uri_to_type_id(member_val["value"])
            if member_key:
                pos = int(pos_val["value"])
                role = binding.get("role", {}).get("value", "")
                members[elem_key].append((pos, member_key, role))

        pred_val = binding.get("p", {})
        val_val = binding.get("v", {})
        if pred_val.get("type") == "uri" and val_val.get("type") == "literal":
            pred_uri = pred_val["value"]
            if "Key:" in pred_uri:
                tags[elem_key][pred_uri.split("Key:")[1]] = val_val["value"]

        if elem_key not in meta:
            row_meta = {}
            for field in _META_FIELDS:
                field_val = binding.get(field, {})
                if field == "changeset" and field_val.get("type") == "uri":
                    uri = field_val["value"]
                    if "/changeset/" in uri:
                        row_meta[field] = uri.split("/changeset/")[1]
                elif field_val.get("type") == "literal":
                    row_meta[field] = field_val["value"].rstrip("Z")
            if row_meta:
                meta[elem_key] = row_meta

    for elem_members in members.values():
        elem_members.sort()

    return members, coords, tags, meta


def test_translated_out_meta_nodes() -> None:
    query = "node[name=Ocotillo]; out meta;"
    op_members, op_coords, op_tags, op_meta = _overpass_meta(query)
    ql_members, ql_coords, ql_tags, ql_meta = _qlever_meta(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    _assert_node_coords(op_coords, ql_coords)
    assert op_tags == ql_tags
    assert op_meta == ql_meta


def test_translated_out_meta_ways() -> None:
    query = "way[name=Ocotillo]; out meta;"
    op_members, _, op_tags, op_meta = _overpass_meta(query)
    ql_members, _, ql_tags, ql_meta = _qlever_meta(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags
    assert op_meta == ql_meta


def test_translated_out_meta_relations() -> None:
    query = "relation[name=Ocotillo]; out meta;"
    op_members, _, op_tags, op_meta = _overpass_meta(query)
    ql_members, _, ql_tags, ql_meta = _qlever_meta(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags
    assert op_meta == ql_meta


def test_translated_out_meta_nwr() -> None:
    query = "nwr[name=Ocotillo]; out meta;"
    op_members, op_coords, op_tags, op_meta = _overpass_meta(query)
    ql_members, ql_coords, ql_tags, ql_meta = _qlever_meta(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    _assert_node_coords(op_coords, ql_coords)
    assert op_tags == ql_tags
    assert op_meta == ql_meta


# ---------------------------------------------------------------------------
# out geom
# ---------------------------------------------------------------------------

# (element_key, member_pos) -> list of (lat, lon) along the member's geometry.
# Node members contribute a single point; way members contribute the full
# coordinate sequence; sub-relation members are omitted (no geometry attached).
_GeomMap = dict[tuple[str, int], list[tuple[float, float]]]

_GeomData = tuple[
    dict[str, list[tuple[int, str, str]]],
    dict[str, tuple[float, float]],
    dict[str, dict[str, str]],
    _GeomMap,
]


def _parse_wkt_coords(wkt: str) -> list[tuple[float, float]]:
    """Parse WKT POINT/LINESTRING/POLYGON and return [(lat, lon), ...].

    For POLYGON, returns the outer ring; inner rings (holes) are ignored.
    """
    s = wkt.strip()
    if s.startswith("POINT("):
        return [_parse_wkt_point(s)]
    if s.startswith("LINESTRING("):
        body = s.removeprefix("LINESTRING(").removesuffix(")")
    elif s.startswith("POLYGON("):
        body = s.removeprefix("POLYGON((").split("))", 1)[0]
    else:
        return []
    result = []
    for pair in body.split(","):
        lon_str, lat_str = pair.strip().split()
        result.append((float(lat_str), float(lon_str)))
    return result


def _overpass_geom(query: str) -> _GeomData:
    """Execute Overpass out geom and return (members, node_coords, tags, geom)."""
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    members: dict[str, list[tuple[int, str, str]]] = {}
    coords: dict[str, tuple[float, float]] = {}
    tags: dict[str, dict[str, str]] = {}
    geom: _GeomMap = {}
    for elem in response.json().get("elements", []):
        eid = f"{elem['type']}/{elem['id']}"
        if elem["type"] == "node":
            members[eid] = []
            coords[eid] = (elem["lat"], elem["lon"])
        elif elem["type"] == "way":
            nodes = elem.get("nodes", [])
            geometry = elem.get("geometry", [])
            members[eid] = [(i, f"node/{nid}", "") for i, nid in enumerate(nodes)]
            for i, g in enumerate(geometry):
                geom[(eid, i)] = [(g["lat"], g["lon"])]
        elif elem["type"] == "relation":
            members[eid] = [
                (i, f"{m['type']}/{m['ref']}", m.get("role", ""))
                for i, m in enumerate(elem.get("members", []))
            ]
            for i, m in enumerate(elem.get("members", [])):
                if "geometry" in m:
                    geom[(eid, i)] = [(g["lat"], g["lon"]) for g in m["geometry"]]
                elif "lat" in m:
                    geom[(eid, i)] = [(m["lat"], m["lon"])]
        tags[eid] = elem.get("tags", {})
    return members, coords, tags, geom


def _qlever_geom(sparql: str) -> _GeomData:
    """Execute SPARQL out geom query and return (members, node_coords, tags, geom)."""
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    data = response.json()
    elem_var = data.get("head", {}).get("vars", [""])[0]

    members: dict[str, list[tuple[int, str, str]]] = {}
    coords: dict[str, tuple[float, float]] = {}
    tags: dict[str, dict[str, str]] = {}
    geom: _GeomMap = {}
    for binding in data.get("results", {}).get("bindings", []):
        elem_val = binding.get(elem_var, {})
        if elem_val.get("type") != "uri":
            continue
        elem_key = _uri_to_type_id(elem_val["value"])
        if elem_key is None:
            continue
        if elem_key not in members:
            members[elem_key] = []
        if elem_key not in tags:
            tags[elem_key] = {}

        wkt_val = binding.get("wkt")
        if wkt_val and wkt_val.get("type") == "literal":
            wkt_str = wkt_val["value"]
            if wkt_str.startswith("POINT("):
                coords[elem_key] = _parse_wkt_point(wkt_str)

        member_val = binding.get("member")
        pos_val = binding.get("pos")
        if member_val and member_val.get("type") == "uri" and pos_val:
            member_key = _uri_to_type_id(member_val["value"])
            if member_key:
                pos = int(pos_val["value"])
                role = binding.get("role", {}).get("value", "")
                members[elem_key].append((pos, member_key, role))
                member_wkt = binding.get("member_wkt", {})
                if member_wkt.get("type") == "literal":
                    member_coords = _parse_wkt_coords(member_wkt["value"])
                    if member_coords:
                        geom[(elem_key, pos)] = member_coords

        pred_val = binding.get("p", {})
        val_val = binding.get("v", {})
        if pred_val.get("type") == "uri" and val_val.get("type") == "literal":
            pred_uri = pred_val["value"]
            if "Key:" in pred_uri:
                tags[elem_key][pred_uri.split("Key:")[1]] = val_val["value"]

    for elem_members in members.values():
        elem_members.sort()

    return members, coords, tags, geom


def _assert_geom(op: _GeomMap, ql: _GeomMap) -> None:
    assert set(op) == set(ql), f"geom key mismatch: {set(op) ^ set(ql)}"
    for key in op:
        op_coords = op[key]
        ql_coords = ql[key]
        assert len(op_coords) == len(ql_coords), (
            f"{key} coord-count mismatch: op={len(op_coords)} ql={len(ql_coords)}"
        )
        for (op_lat, op_lon), (ql_lat, ql_lon) in zip(op_coords, ql_coords):
            assert op_lat == pytest.approx(ql_lat, abs=1e-6), f"{key} lat mismatch"
            assert op_lon == pytest.approx(ql_lon, abs=1e-6), f"{key} lon mismatch"


def test_translated_out_geom_node() -> None:
    # node: just a POINT; no members, no member geometries.
    query = "node(1); out geom;"
    op_members, op_coords, op_tags, op_geom = _overpass_geom(query)
    ql_members, ql_coords, ql_tags, ql_geom = _qlever_geom(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    _assert_node_coords(op_coords, ql_coords)
    assert op_tags == ql_tags
    _assert_geom(op_geom, ql_geom)


def test_translated_out_geom_way_open() -> None:
    # open way: per-member POINT coords compose into a LINESTRING-shaped path.
    query = "way(6007783); out geom;"
    op_members, _, op_tags, op_geom = _overpass_geom(query)
    ql_members, _, ql_tags, ql_geom = _qlever_geom(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags
    _assert_geom(op_geom, ql_geom)


def test_translated_out_geom_way_closed() -> None:
    # closed way: first node repeats as last; geometry forms a POLYGON-shaped ring.
    query = "way(100); out geom;"
    op_members, _, op_tags, op_geom = _overpass_geom(query)
    ql_members, _, ql_tags, ql_geom = _qlever_geom(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags
    _assert_geom(op_geom, ql_geom)


def test_translated_out_geom_relation_mixed_members() -> None:
    # mixed-member relation: one way member (LINESTRING/POLYGON) + one node
    # member (POINT). Exercises both branches of per-member WKT decoding.
    query = "relation(18375544); out geom;"
    op_members, _, op_tags, op_geom = _overpass_geom(query)
    ql_members, _, ql_tags, ql_geom = _qlever_geom(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags
    _assert_geom(op_geom, ql_geom)


@pytest.mark.xfail(
    reason=(
        "Pre-existing role divergence for blank relation member roles: Overpass "
        "reports '' (empty), QLever/osm2rdf reports 'member'. Unrelated to geom "
        "translation — the geom assertions in this test would otherwise pass "
        "(both backends report no per-member geometry for sub-relation members). "
        "Pending investigation into whether all blank relation roles get "
        "rewritten to 'member' in osm2rdf, in which case a translator-level "
        "rewrite back to '' would clash with members whose role is genuinely "
        "'member'."
    ),
    strict=True,
)
def test_translated_out_geom_relation_subrelation_members() -> None:
    # sub-relation-only relation: OPTIONAL member geometry stays unbound; the
    # member rows must still appear in the result.
    query = "relation(20513114); out geom;"
    op_members, _, op_tags, op_geom = _overpass_geom(query)
    ql_members, _, ql_tags, ql_geom = _qlever_geom(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags
    _assert_geom(op_geom, ql_geom)
    assert op_geom == {}, "expected no per-member geometry for sub-relation members"


# ---------------------------------------------------------------------------
# out bb
# ---------------------------------------------------------------------------

# Top-level bounds as (minlat, minlon, maxlat, maxlon) per element key.
_BoundsMap = dict[str, tuple[float, float, float, float]]


def _bounds_from_coords(
    coords: list[tuple[float, float]],
) -> tuple[float, float, float, float] | None:
    if not coords:
        return None
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    return min(lats), min(lons), max(lats), max(lons)


def _overpass_bb_ids(query: str) -> tuple[dict[str, tuple[float, float]], _BoundsMap]:
    """Execute Overpass `out ids bb` and return (node_coords, bounds)."""
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    coords: dict[str, tuple[float, float]] = {}
    bounds: _BoundsMap = {}
    for elem in response.json().get("elements", []):
        eid = f"{elem['type']}/{elem['id']}"
        if "lat" in elem:
            coords[eid] = (elem["lat"], elem["lon"])
        if "bounds" in elem:
            b = elem["bounds"]
            bounds[eid] = (b["minlat"], b["minlon"], b["maxlat"], b["maxlon"])
    return coords, bounds


def _qlever_bb_ids(sparql: str) -> tuple[dict[str, tuple[float, float]], _BoundsMap]:
    """Execute SPARQL `out ids bb` query and return (node_coords, bounds).

    For nodes, the element's own POINT WKT yields lat/lon directly. For ways
    and relations, the LINESTRING/POLYGON WKT is reduced to its min/max
    coordinates to form a bounds tuple.
    """
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    data = response.json()
    elem_var = data.get("head", {}).get("vars", [""])[0]
    coords: dict[str, tuple[float, float]] = {}
    bounds: _BoundsMap = {}
    for binding in data.get("results", {}).get("bindings", []):
        elem_val = binding.get(elem_var, {})
        if elem_val.get("type") != "uri":
            continue
        elem_key = _uri_to_type_id(elem_val["value"])
        if elem_key is None:
            continue
        wkt_val = binding.get("bb_wkt")
        if not (wkt_val and wkt_val.get("type") == "literal"):
            continue
        wkt_str = wkt_val["value"]
        if wkt_str.startswith("POINT("):
            coords[elem_key] = _parse_wkt_point(wkt_str)
        else:
            parsed = _parse_wkt_coords(wkt_str)
            b = _bounds_from_coords(parsed)
            if b is not None:
                bounds[elem_key] = b
    return coords, bounds


def _assert_bounds(op: _BoundsMap, ql: _BoundsMap) -> None:
    assert set(op) == set(ql), f"bounds key mismatch: {set(op) ^ set(ql)}"
    for key in op:
        op_b = op[key]
        ql_b = ql[key]
        for label, ov, qv in zip(("minlat", "minlon", "maxlat", "maxlon"), op_b, ql_b):
            assert ov == pytest.approx(qv, abs=1e-6), f"{key} {label} mismatch"


def test_translated_out_bb_ids_node() -> None:
    # node + bb: emits lat/lon (no bounds key).
    query = "node(1); out ids bb;"
    op_coords, op_bounds = _overpass_bb_ids(query)
    ql_coords, ql_bounds = _qlever_bb_ids(_compose_out_query(query))
    _assert_node_coords(op_coords, ql_coords)
    assert op_bounds == ql_bounds == {}


def test_translated_out_bb_ids_way_open() -> None:
    query = "way(6007783); out ids bb;"
    _, op_bounds = _overpass_bb_ids(query)
    _, ql_bounds = _qlever_bb_ids(_compose_out_query(query))
    _assert_bounds(op_bounds, ql_bounds)


def test_translated_out_bb_ids_way_closed() -> None:
    query = "way(100); out ids bb;"
    _, op_bounds = _overpass_bb_ids(query)
    _, ql_bounds = _qlever_bb_ids(_compose_out_query(query))
    _assert_bounds(op_bounds, ql_bounds)


def test_translated_out_bb_ids_relation() -> None:
    query = "relation(18375544); out ids bb;"
    _, op_bounds = _overpass_bb_ids(query)
    _, ql_bounds = _qlever_bb_ids(_compose_out_query(query))
    _assert_bounds(op_bounds, ql_bounds)


# ---------------------------------------------------------------------------
# out tags bb
# ---------------------------------------------------------------------------


def _overpass_bb_tags(
    query: str,
) -> tuple[dict[str, tuple[float, float]], _BoundsMap, dict[str, dict[str, str]]]:
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    coords: dict[str, tuple[float, float]] = {}
    bounds: _BoundsMap = {}
    tags: dict[str, dict[str, str]] = {}
    for elem in response.json().get("elements", []):
        eid = f"{elem['type']}/{elem['id']}"
        if "lat" in elem:
            coords[eid] = (elem["lat"], elem["lon"])
        if "bounds" in elem:
            b = elem["bounds"]
            bounds[eid] = (b["minlat"], b["minlon"], b["maxlat"], b["maxlon"])
        tags[eid] = elem.get("tags", {})
    return coords, bounds, tags


def _qlever_bb_tags(
    sparql: str,
) -> tuple[dict[str, tuple[float, float]], _BoundsMap, dict[str, dict[str, str]]]:
    response = requests.post(
        QLEVER_URL,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    data = response.json()
    elem_var = data.get("head", {}).get("vars", [""])[0]
    coords: dict[str, tuple[float, float]] = {}
    bounds: _BoundsMap = {}
    tags: dict[str, dict[str, str]] = {}
    for binding in data.get("results", {}).get("bindings", []):
        elem_val = binding.get(elem_var, {})
        if elem_val.get("type") != "uri":
            continue
        elem_key = _uri_to_type_id(elem_val["value"])
        if elem_key is None:
            continue
        if elem_key not in tags:
            tags[elem_key] = {}

        wkt_val = binding.get("bb_wkt")
        if wkt_val and wkt_val.get("type") == "literal":
            wkt_str = wkt_val["value"]
            if wkt_str.startswith("POINT("):
                coords[elem_key] = _parse_wkt_point(wkt_str)
            else:
                parsed = _parse_wkt_coords(wkt_str)
                b = _bounds_from_coords(parsed)
                if b is not None:
                    bounds[elem_key] = b

        pred_val = binding.get("p", {})
        val_val = binding.get("v", {})
        if pred_val.get("type") == "uri" and val_val.get("type") == "literal":
            pred_uri = pred_val["value"]
            if "Key:" in pred_uri:
                tags[elem_key][pred_uri.split("Key:")[1]] = val_val["value"]

    return coords, bounds, tags


def test_translated_out_bb_tags_node() -> None:
    # node + tags + bb: tags carry lat/lon (no bounds for nodes).
    query = "node(1); out tags bb;"
    op_coords, op_bounds, op_tags = _overpass_bb_tags(query)
    ql_coords, ql_bounds, ql_tags = _qlever_bb_tags(_compose_out_query(query))
    _assert_node_coords(op_coords, ql_coords)
    assert op_bounds == ql_bounds == {}
    assert op_tags == ql_tags


def test_translated_out_bb_tags_way() -> None:
    query = "way(100); out tags bb;"
    _, op_bounds, op_tags = _overpass_bb_tags(query)
    _, ql_bounds, ql_tags = _qlever_bb_tags(_compose_out_query(query))
    _assert_bounds(op_bounds, ql_bounds)
    assert op_tags == ql_tags


# ---------------------------------------------------------------------------
# out body bb (skel/body/meta path: bounds derived from per-member WKTs)
# ---------------------------------------------------------------------------


def test_translated_out_bb_body_relation() -> None:
    # body + bb: members + tags + bounds. The translator collects per-member
    # WKTs via the include_member_wkt path; bounds is the union of all member
    # coordinates.
    query = "relation(18375544); out body bb;"
    op_members, _, op_tags, op_geom = _overpass_geom(query)
    ql_members, _, ql_tags, ql_geom = _qlever_geom(_compose_out_query(query))
    assert set(op_members) == set(ql_members)
    for key in op_members:
        assert op_members[key] == ql_members[key]
    assert op_tags == ql_tags

    # Compute bounds from per-member coords on both sides and compare against
    # the Overpass top-level bounds.
    response = requests.post(OVERPASS_URL, data={"data": f"[out:json];{query}"})
    response.raise_for_status()
    op_top_bounds: _BoundsMap = {}
    for elem in response.json().get("elements", []):
        if "bounds" in elem:
            b = elem["bounds"]
            op_top_bounds[f"{elem['type']}/{elem['id']}"] = (
                b["minlat"],
                b["minlon"],
                b["maxlat"],
                b["maxlon"],
            )

    ql_bounds: _BoundsMap = {}
    by_elem: dict[str, list[tuple[float, float]]] = {}
    for (elem_key, _pos), coords in ql_geom.items():
        by_elem.setdefault(elem_key, []).extend(coords)
    for elem_key, all_coords in by_elem.items():
        b = _bounds_from_coords(all_coords)
        if b is not None:
            ql_bounds[elem_key] = b

    _assert_bounds(op_top_bounds, ql_bounds)


# ---------------------------------------------------------------------------
# out debug
# ---------------------------------------------------------------------------


def test_out_debug_one_stmt() -> None:
    import asyncio

    query_text = (
        "[out:raw]; way(381029345) -> .a; node(w.a) -> .b; way(bn.b); out debug;"
    )

    async def run() -> str:
        tree = parse(query_text)
        query = QueryContext(text=query_text, tree=tree)
        content, _media_type = await interpreter.initialize(query)
        chunks = []
        async for chunk in content:
            chunks.append(chunk)
        return "".join(chunks)

    output = asyncio.run(run())
    print(output)
    assert "output_set:" in output
    assert "result_variable:" in output
    assert "distinct:" in output
    assert "materialize:" in output
    assert "prefixes:" in output
    assert "where_clauses:" in output
    assert "injections:" in output
