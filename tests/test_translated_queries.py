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
