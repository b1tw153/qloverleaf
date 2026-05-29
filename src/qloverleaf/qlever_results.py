from __future__ import annotations

from typing import Any

_COUNT_TYPE_TAGS: dict[str, str] = {
    "https://www.openstreetmap.org/node": "nodes",
    "https://www.openstreetmap.org/way": "ways",
    "https://www.openstreetmap.org/relation": "relations",
}


def parse_count(data: dict[str, Any]) -> dict[str, Any]:
    """Parse a QLever count result into an Overpass-shaped count element.

    The SPARQL query groups by ?type and counts distinct elements per type.
    Returns a single element dict with type "count", id 0, and string counts
    in tags (nodes, ways, relations, total).
    """
    counts: dict[str, int] = {"nodes": 0, "ways": 0, "relations": 0}
    for binding in data.get("results", {}).get("bindings", []):
        type_val = binding.get("type", {})
        count_val = binding.get("count", {})
        if type_val.get("type") != "uri" or count_val.get("type") != "literal":
            continue
        tag = _COUNT_TYPE_TAGS.get(type_val["value"])
        if tag:
            counts[tag] = int(count_val["value"])

    total = sum(counts.values())
    return {
        "type": "count",
        "id": 0,
        "tags": {
            "nodes": str(counts["nodes"]),
            "ways": str(counts["ways"]),
            "relations": str(counts["relations"]),
            "total": str(total),
        },
    }
