import pytest
import requests

from qloverleaf.composer import compose
from qloverleaf.interpreter import SetState, SetStateEntry
from qloverleaf.parser import parse
from qloverleaf.transformer import OverpassTransformer
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

# TODO: Requires set composition - deferred


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
