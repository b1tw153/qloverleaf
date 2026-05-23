import requests

from qloverleaf.interpreter import SetState
from qloverleaf.parser import parse
from qloverleaf.transform import OverpassTransformer
from qloverleaf.translator import SparqlPattern, render_query, translate

OVERPASS_URL = "http://localhost/api/interpreter"
QLEVER_URL = "https://qlever.dev/api/osm-planet"


def _translate(text: str) -> list[SparqlPattern]:
    query = OverpassTransformer().transform(parse(text))
    return translate(query.statements[0])


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

# TODO: Requires set composition - deferred


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

# TODO: Requires set composition - deferred


# ---------------------------------------------------------------------------
# RecurseFilter
# ---------------------------------------------------------------------------

# TODO: Requires set composition - deferred


# ---------------------------------------------------------------------------
# WayCountFilter
# ---------------------------------------------------------------------------

# TODO: Requires set composition - deferred


# ---------------------------------------------------------------------------
# SetFilter
# ---------------------------------------------------------------------------

# TODO: Requires set composition - deferred


# ---------------------------------------------------------------------------
# PivotFilter
# ---------------------------------------------------------------------------

# TODO: Requires set composition - deferred
