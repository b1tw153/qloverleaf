from typing import Any

import httpx

from qloverleaf.transform import ElementType
from qloverleaf.translator import SparqlPattern

QLEVER_ENDPOINT = "https://qlever.dev/api/osm-planet"

SPARQL_PREFIXES: dict[str, str] = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "osm": "https://www.openstreetmap.org/",
    "osmkey": "https://www.openstreetmap.org/wiki/Key:",
    "osmnode": "https://www.openstreetmap.org/node/",
    "osmway": "https://www.openstreetmap.org/way/",
    "osmrel": "https://www.openstreetmap.org/relation/",
    "osmeta": "https://www.openstreetmap.org/meta/",
    "geo": "http://www.opengis.net/ont/geosparql#",
    "geof": "http://www.opengis.net/def/function/geosparql/",
}

_URI_PREFIXES: list[tuple[str, ElementType]] = [
    ("https://www.openstreetmap.org/node/", ElementType.NODE),
    ("https://www.openstreetmap.org/way/", ElementType.WAY),
    ("https://www.openstreetmap.org/relation/", ElementType.RELATION),
]

SetState = dict[str, list[tuple[ElementType, str]]]


def uri_to_element_type(uri: str) -> ElementType:
    for prefix, element_type in _URI_PREFIXES:
        if uri.startswith(prefix):
            return element_type
    raise ValueError(f"Unrecognized OSM URI: {uri}")


def render_query(pattern: SparqlPattern, set_state: SetState) -> str:
    lines: list[str] = []

    for prefix in sorted(pattern.prefixes):
        uri = SPARQL_PREFIXES[prefix]
        lines.append(f"PREFIX {prefix}: <{uri}>")

    distinct = "DISTINCT " if pattern.distinct else ""
    lines.append(f"SELECT {distinct}{pattern.result_variable} WHERE {{")

    for inj in pattern.injections:
        uris = set_state.get(inj.set_name, [])
        uri_list = " ".join(f"<{u}>" for _, u in uris)
        lines.append(f"  VALUES {inj.sparql_var} {{ {uri_list} }}")

    for clause in pattern.where_clauses:
        lines.append(f"  {clause}")

    lines.append("}")
    return "\n".join(lines)


def parse_results(
    data: dict[str, Any], var_name: str
) -> list[tuple[ElementType, str]]:
    results: list[tuple[ElementType, str]] = []
    for binding in data["results"]["bindings"]:
        if var_name in binding:
            uri = binding[var_name]["value"]
            results.append((uri_to_element_type(uri), uri))
    return results


async def query_qlever(sparql: str, client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.post(
        QLEVER_ENDPOINT,
        data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result
