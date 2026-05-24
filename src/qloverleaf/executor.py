from typing import Any

import httpx

from qloverleaf.transformer import ElementType

QLEVER_ENDPOINT = "https://qlever.dev/api/osm-planet"

_URI_PREFIXES: list[tuple[str, ElementType]] = [
    ("https://www.openstreetmap.org/node/", ElementType.NODE),
    ("https://www.openstreetmap.org/way/", ElementType.WAY),
    ("https://www.openstreetmap.org/relation/", ElementType.RELATION),
]


def uri_to_element_type(uri: str) -> ElementType:
    for prefix, element_type in _URI_PREFIXES:
        if uri.startswith(prefix):
            return element_type
    raise ValueError(f"Unrecognized OSM URI: {uri}")


def parse_results(data: dict[str, Any], var_name: str) -> list[tuple[ElementType, str]]:
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
