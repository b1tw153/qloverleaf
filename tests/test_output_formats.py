import asyncio
import json
from typing import Any, cast

import requests

from qloverleaf import interpreter
from qloverleaf.parser import parse
from qloverleaf.query_context import QueryContext

OVERPASS_URL = "http://localhost/api/interpreter"


def _run_query(query_text: str) -> str:
    async def run() -> str:
        tree = parse(query_text)
        query = QueryContext(text=query_text, tree=tree)
        content, _media_type = await interpreter.initialize(query)
        chunks = []
        async for chunk in content:
            chunks.append(chunk)
        return "".join(chunks)

    return asyncio.run(run())


# TODO: Document the limitation that QLever only stores six digits for coordinates
# TODO: Review type declarations to avoid the Any argument and Any return
def _round_floats(obj: Any, places: int = 6) -> Any:
    if isinstance(obj, float):
        return round(obj, places)
    if isinstance(obj, dict):
        return {k: _round_floats(v, places) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(item, places) for item in obj]
    return obj


def _overpass_elements(query_text: str) -> list[dict[str, Any]]:
    response = requests.post(OVERPASS_URL, data={"data": query_text})
    response.raise_for_status()
    return cast(list[dict[str, Any]], _round_floats(response.json()["elements"]))


# ---------------------------------------------------------------------------
# out debug
# ---------------------------------------------------------------------------


def test_out_debug_one_stmt() -> None:
    query_text = (
        "[out:raw]; way(381029345) -> .a; node(w.a) -> .b; way(bn.b); out debug;"
    )
    output = _run_query(query_text)
    print(output)
    assert "output_set:" in output
    assert "result_variable:" in output
    assert "distinct:" in output
    assert "materialize:" in output
    assert "prefixes:" in output
    assert "where_clauses:" in output
    assert "injections:" in output


# ---------------------------------------------------------------------------
# out json node
# ---------------------------------------------------------------------------


def test_out_json_node_ids() -> None:
    query_text = "[out:json]; node(1); out ids;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_node_ids_center() -> None:
    query_text = "[out:json]; node(1); out ids center;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_node_ids_bb() -> None:
    query_text = "[out:json]; node(1); out ids bb;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_node_tags() -> None:
    query_text = "[out:json]; node(1); out tags;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_node_skel() -> None:
    query_text = "[out:json]; node(1); out skel;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_node_body() -> None:
    query_text = "[out:json]; node(1); out body;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_node_meta() -> None:
    query_text = "[out:json]; node(2); out meta;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_node_geom() -> None:
    query_text = "[out:json]; node(1); out geom;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_node_geom_meta() -> None:
    query_text = "[out:json]; node(2); out geom meta;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


# ---------------------------------------------------------------------------
# out json way
# ---------------------------------------------------------------------------


def test_out_json_way_ids() -> None:
    query_text = "[out:json]; way(100); out ids;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_way_ids_center() -> None:
    query_text = "[out:json]; way(100); out ids center;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_way_ids_bb() -> None:
    query_text = "[out:json]; way(100); out ids bb;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_way_tags() -> None:
    query_text = "[out:json]; way(100); out tags;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_way_skel() -> None:
    query_text = "[out:json]; way(100); out skel;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_way_body() -> None:
    query_text = "[out:json]; way(100); out body;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_way_meta() -> None:
    query_text = "[out:json]; way(100); out meta;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_way_geom() -> None:
    query_text = "[out:json]; way(100); out geom;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_way_geom_meta() -> None:
    query_text = "[out:json]; way(100); out geom meta;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


# ---------------------------------------------------------------------------
# out json rel
# ---------------------------------------------------------------------------


def test_out_json_rel_ids() -> None:
    query_text = "[out:json]; rel(18375544); out ids;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_ids_center() -> None:
    query_text = "[out:json]; rel(18375544); out ids center;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_ids_bb() -> None:
    query_text = "[out:json]; rel(11837554400); out ids bb;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_tags() -> None:
    query_text = "[out:json]; rel(18375544); out tags;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_skel() -> None:
    query_text = "[out:json]; rel(18375544); out skel;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_body() -> None:
    query_text = "[out:json]; rel(18375544); out body;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_meta() -> None:
    query_text = "[out:json]; rel(18375544); out meta;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_geom() -> None:
    query_text = "[out:json]; rel(18375544); out geom;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_geom_meta() -> None:
    query_text = "[out:json]; rel(18375544); out geom meta;"
    output = _run_query(query_text)
    elements = json.loads(output)["elements"]
    assert elements == _overpass_elements(query_text)
