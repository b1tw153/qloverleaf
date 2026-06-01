import asyncio
import json
import xml.etree.ElementTree as ET
from typing import Any, cast

import httpx
import pytest

from qloverleaf import interpreter
from qloverleaf.parser import parse
from qloverleaf.query_context import QueryContext

pytestmark = pytest.mark.live

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


# QLever only stores six decimal places for POINT coordinates but it stores seven
# decimal places for WKTs for ways and relations. Reported bug in osm2rdf:
# https://github.com/ad-freiburg/osm2rdf/issues/135
# TODO: Remove this rounding when the bug is fixed and QLever is updated
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
    response = httpx.post(OVERPASS_URL, data={"data": query_text})
    response.raise_for_status()
    return cast(list[dict[str, Any]], _round_floats(response.json()["elements"]))


def _parse_xml_element(el: ET.Element) -> dict[str, Any]:
    out: dict[str, Any] = {"type": el.tag, "id": int(el.attrib["id"])}

    if "lat" in el.attrib:
        out["lat"] = float(el.attrib["lat"])
        out["lon"] = float(el.attrib["lon"])

    for field in ("version", "uid"):
        if field in el.attrib:
            out[field] = int(el.attrib[field])
    for field in ("timestamp", "user"):
        if field in el.attrib:
            out[field] = el.attrib[field]
    if "changeset" in el.attrib:
        out["changeset"] = int(el.attrib["changeset"])

    nodes: list[int] = []
    geometry: list[dict[str, float]] = []
    members: list[dict[str, Any]] = []
    tags: dict[str, str] = {}

    for child in el:
        if child.tag == "tag":
            tags[child.attrib["k"]] = child.attrib["v"]
        elif child.tag == "nd":
            if "ref" in child.attrib:
                nodes.append(int(child.attrib["ref"]))
            if "lat" in child.attrib:
                geometry.append(
                    {
                        "lat": float(child.attrib["lat"]),
                        "lon": float(child.attrib["lon"]),
                    }
                )
        elif child.tag == "member":
            member: dict[str, Any] = {
                "type": child.attrib["type"],
                "ref": int(child.attrib["ref"]),
                "role": child.attrib.get("role", ""),
            }
            if "lat" in child.attrib:
                member["lat"] = float(child.attrib["lat"])
                member["lon"] = float(child.attrib["lon"])
            member_nds = [
                {"lat": float(nd.attrib["lat"]), "lon": float(nd.attrib["lon"])}
                for nd in child
                if nd.tag == "nd" and "lat" in nd.attrib
            ]
            if member_nds:
                member["geometry"] = member_nds
            members.append(member)
        elif child.tag == "bounds":
            out["bounds"] = {
                "minlat": float(child.attrib["minlat"]),
                "minlon": float(child.attrib["minlon"]),
                "maxlat": float(child.attrib["maxlat"]),
                "maxlon": float(child.attrib["maxlon"]),
            }
        elif child.tag == "center":
            out["center"] = {
                "lat": float(child.attrib["lat"]),
                "lon": float(child.attrib["lon"]),
            }

    if nodes:
        out["nodes"] = nodes
    if geometry:
        out["geometry"] = geometry
    if members:
        out["members"] = members
    if tags:
        out["tags"] = tags

    return out


def _parse_xml_elements(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    elements = [
        _parse_xml_element(child)
        for child in root
        if child.tag in ("node", "way", "relation")
    ]
    return cast(list[dict[str, Any]], _round_floats(elements))


def _overpass_elements_xml(query_text: str) -> list[dict[str, Any]]:
    response = httpx.post(OVERPASS_URL, data={"data": query_text})
    response.raise_for_status()
    return _parse_xml_elements(response.text)


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
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_node_ids_center() -> None:
    query_text = "[out:json]; node(1); out ids center;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_node_ids_bb() -> None:
    query_text = "[out:json]; node(1); out ids bb;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_node_tags() -> None:
    query_text = "[out:json]; node(1); out tags;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_node_skel() -> None:
    query_text = "[out:json]; node(1); out skel;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_node_body() -> None:
    query_text = "[out:json]; node(1); out body;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_node_meta() -> None:
    query_text = "[out:json]; node(2); out meta;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_node_geom() -> None:
    query_text = "[out:json]; node(1); out geom;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_node_geom_meta() -> None:
    query_text = "[out:json]; node(2); out geom meta;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


# ---------------------------------------------------------------------------
# out json way
# ---------------------------------------------------------------------------


def test_out_json_way_ids() -> None:
    query_text = "[out:json]; way(414876262); out ids;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_way_ids_center() -> None:
    query_text = "[out:json]; way(414876262); out ids center;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_way_ids_bb() -> None:
    query_text = "[out:json]; way(414876262); out ids bb;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_way_tags() -> None:
    query_text = "[out:json]; way(414876262); out tags;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_way_skel() -> None:
    query_text = "[out:json]; way(414876262); out skel;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_way_body() -> None:
    query_text = "[out:json]; way(100); out body;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_way_meta() -> None:
    query_text = "[out:json]; way(414876262); out meta;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_way_geom() -> None:
    query_text = "[out:json]; way(414876262); out geom;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_way_geom_meta() -> None:
    query_text = "[out:json]; way(414876262); out geom meta;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


# ---------------------------------------------------------------------------
# out json rel
# ---------------------------------------------------------------------------


def test_out_json_rel_ids() -> None:
    query_text = "[out:json]; rel(13904654); out ids;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_ids_center() -> None:
    query_text = "[out:json]; rel(13904654); out ids center;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_ids_bb() -> None:
    query_text = "[out:json]; rel(13904654); out ids bb;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_tags() -> None:
    query_text = "[out:json]; rel(13904654); out tags;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_skel() -> None:
    query_text = "[out:json]; rel(13904654); out skel;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_body() -> None:
    query_text = "[out:json]; rel(13904654); out body;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_meta() -> None:
    query_text = "[out:json]; rel(13904654); out meta;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_geom() -> None:
    query_text = "[out:json]; rel(13904654); out geom;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


def test_out_json_rel_geom_meta() -> None:
    query_text = "[out:json]; rel(13904654); out geom meta;"
    output = _run_query(query_text)
    elements = _round_floats(json.loads(output)["elements"])
    assert elements == _overpass_elements(query_text)


# ---------------------------------------------------------------------------
# out xml node
# ---------------------------------------------------------------------------


def test_out_xml_node_ids() -> None:
    query_text = "[out:xml]; node(1); out ids;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_node_ids_center() -> None:
    query_text = "[out:xml]; node(1); out ids center;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_node_ids_bb() -> None:
    query_text = "[out:xml]; node(1); out ids bb;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_node_tags() -> None:
    query_text = "[out:xml]; node(1); out tags;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_node_skel() -> None:
    query_text = "[out:xml]; node(1); out skel;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_node_body() -> None:
    query_text = "[out:xml]; node(1); out body;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_node_meta() -> None:
    query_text = "[out:xml]; node(2); out meta;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_node_geom() -> None:
    query_text = "[out:xml]; node(1); out geom;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_node_geom_meta() -> None:
    query_text = "[out:xml]; node(2); out geom meta;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


# ---------------------------------------------------------------------------
# out xml way
# ---------------------------------------------------------------------------


def test_out_xml_way_ids() -> None:
    query_text = "[out:xml]; way(414876262); out ids;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_way_ids_center() -> None:
    query_text = "[out:xml]; way(414876262); out ids center;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_way_ids_bb() -> None:
    query_text = "[out:xml]; way(414876262); out ids bb;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_way_tags() -> None:
    query_text = "[out:xml]; way(100); out tags;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_way_skel() -> None:
    query_text = "[out:xml]; way(414876262); out skel;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_way_body() -> None:
    query_text = "[out:xml]; way(414876262); out body;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_way_meta() -> None:
    query_text = "[out:xml]; way(414876262); out meta;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_way_geom() -> None:
    query_text = "[out:xml]; way(414876262); out geom;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_way_geom_meta() -> None:
    query_text = "[out:xml]; way(414876262); out geom meta;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


# ---------------------------------------------------------------------------
# out xml rel
# ---------------------------------------------------------------------------


def test_out_xml_rel_ids() -> None:
    query_text = "[out:xml]; rel(13904654); out ids;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_rel_ids_center() -> None:
    query_text = "[out:xml]; rel(13904654); out ids center;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_rel_ids_bb() -> None:
    query_text = "[out:xml]; rel(13904654); out ids bb;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_rel_tags() -> None:
    query_text = "[out:xml]; rel(13904654); out tags;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_rel_skel() -> None:
    query_text = "[out:xml]; rel(13904654); out skel;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_rel_body() -> None:
    query_text = "[out:xml]; rel(13904654); out body;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_rel_meta() -> None:
    query_text = "[out:xml]; rel(13904654); out meta;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_rel_geom() -> None:
    query_text = "[out:xml]; rel(13904654); out geom;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


def test_out_xml_rel_geom_meta() -> None:
    query_text = "[out:xml]; rel(13904654); out geom meta;"
    output = _run_query(query_text)
    elements = _parse_xml_elements(output)
    assert elements == _overpass_elements_xml(query_text)


# TODO: Figure out why the XML for this query is malformed:
# nwr[leisure=golf_course]; nwr(around:0)[office=yes]; out geom;
