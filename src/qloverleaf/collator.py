import math
from typing import Any

from qloverleaf.transformer import OutStatement, OutVerbosity

_COUNT_TYPE_TAGS: dict[str, str] = {
    "https://www.openstreetmap.org/node": "nodes",
    "https://www.openstreetmap.org/way": "ways",
    "https://www.openstreetmap.org/relation": "relations",
}

_URI_TYPE_MAP: list[tuple[str, str]] = [
    ("/node/", "node"),
    ("/way/", "way"),
    ("/relation/", "relation"),
]

_META_FIELDS = ("version", "timestamp", "changeset", "uid", "user")


def parse_wkt_point(wkt: str) -> tuple[float, float]:
    """Parse POINT(lon lat) and return (lat, lon)."""
    coords = wkt.removeprefix("POINT(").removesuffix(")")
    lon_str, lat_str = coords.split()
    return float(lat_str), float(lon_str)


def parse_wkt_coords(wkt: str) -> list[tuple[float, float]]:
    """Parse WKT POINT/LINESTRING/POLYGON and return [(lat, lon), ...].

    For POLYGON, returns the outer ring only.
    """
    s = wkt.strip()
    if s.startswith("POINT("):
        return [parse_wkt_point(s)]
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


def _uri_to_type_id(uri: str) -> tuple[str, int] | None:
    for path, type_str in _URI_TYPE_MAP:
        if path in uri:
            return type_str, int(uri.split(path)[1])
    return None


def _update_bounds(acc: list[float], lat: float, lon: float) -> None:
    if lat < acc[0]:
        acc[0] = lat
    if lon < acc[1]:
        acc[1] = lon
    if lat > acc[2]:
        acc[2] = lat
    if lon > acc[3]:
        acc[3] = lon


def _bounds_dict(acc: list[float]) -> dict[str, float]:
    return {"minlat": acc[0], "minlon": acc[1], "maxlat": acc[2], "maxlon": acc[3]}


def collate_count(data: dict[str, Any]) -> dict[str, Any]:
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


def collate_elements(data: dict[str, Any], stmt: OutStatement) -> list[dict[str, Any]]:
    """Parse QLever SPARQL results into a list of Overpass-shaped element dicts."""
    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return []

    elem_var = data["head"]["vars"][0]

    include_tags = stmt.verbosity in (
        OutVerbosity.TAGS,
        OutVerbosity.BODY,
        OutVerbosity.META,
    )
    include_members = stmt.verbosity in (
        OutVerbosity.SKEL,
        OutVerbosity.BODY,
        OutVerbosity.META,
    )
    include_meta = stmt.verbosity == OutVerbosity.META
    # ids/tags + bb uses a dedicated ?bb_wkt column; skel/body/meta + bb derives
    # bounds from the per-member WKTs that are already collected for geom
    bb_via_wkt = stmt.bb and stmt.verbosity in (OutVerbosity.IDS, OutVerbosity.TAGS)

    accum: dict[str, dict[str, Any]] = {}

    for binding in bindings:
        elem_val = binding.get(elem_var, {})
        if elem_val.get("type") != "uri":
            continue
        uri = elem_val["value"]

        if uri not in accum:
            parsed = _uri_to_type_id(uri)
            if parsed is None:
                continue
            elem_type, elem_id = parsed
            elem: dict[str, Any] = {"type": elem_type, "id": elem_id}
            if include_tags:
                elem["tags"] = {}
            if include_members and elem_type != "node":
                elem["_members"] = []  # [(pos, type, ref, role), ...]
            if (stmt.geom or stmt.bb) and elem_type != "node":
                elem["_bounds_acc"] = [math.inf, math.inf, -math.inf, -math.inf]
            if stmt.geom and elem_type != "node":
                elem["_geom"] = {}  # pos → [(lat, lon), ...]
            if include_meta:
                elem["_meta_done"] = False
            accum[uri] = elem
        else:
            elem = accum[uri]

        elem_type = elem["type"]

        # Node geometry: POINT → lat/lon
        wkt_val = binding.get("wkt")
        if wkt_val and wkt_val.get("type") == "literal" and elem_type == "node":
            wkt_str = wkt_val["value"]
            if wkt_str.startswith("POINT("):
                lat, lon = parse_wkt_point(wkt_str)
                elem["lat"] = lat
                elem["lon"] = lon

        # Member + optional member WKT
        member_val = binding.get("member")
        pos_val = binding.get("pos")
        if (
            member_val
            and member_val.get("type") == "uri"
            and pos_val
            and "_members" in elem
        ):
            member_parsed = _uri_to_type_id(member_val["value"])
            if member_parsed:
                member_type, member_ref = member_parsed
                pos = int(pos_val["value"])
                role = binding.get("role", {}).get("value", "")
                elem["_members"].append((pos, member_type, member_ref, role))

                # Relation member WKT is projected as ?wkt (same column as node geom)
                if wkt_val and wkt_val.get("type") == "literal":
                    coords = parse_wkt_coords(wkt_val["value"])
                    if coords:
                        if stmt.geom:
                            elem["_geom"][pos] = coords
                        if stmt.geom or stmt.bb:
                            for lat, lon in coords:
                                _update_bounds(elem["_bounds_acc"], lat, lon)

        # Way geometry: whole-way WKT from a dedicated branch (no ?member/?pos)
        member_wkt_val = binding.get("member_wkt")
        if (
            member_wkt_val
            and member_wkt_val.get("type") == "literal"
            and elem_type == "way"
        ):
            coords = parse_wkt_coords(member_wkt_val["value"])
            if coords:
                if stmt.geom:
                    elem["_way_geom"] = coords
                if stmt.geom or stmt.bb:
                    for lat, lon in coords:
                        _update_bounds(elem["_bounds_acc"], lat, lon)

        # Tags
        if include_tags:
            pred_val = binding.get("p", {})
            val_val = binding.get("v", {})
            if pred_val.get("type") == "uri" and val_val.get("type") == "literal":
                pred_uri = pred_val["value"]
                if "Key:" in pred_uri:
                    elem["tags"][pred_uri.split("Key:")[1]] = val_val["value"]

        # Meta fields — read once from the first binding (flattened onto all rows)
        if include_meta and not elem["_meta_done"]:
            _extract_meta(elem, binding)

        # Center: nodes get lat/lon inline; ways/relations get center{}
        if stmt.center:
            centroid_val = binding.get("centroid")
            if centroid_val and centroid_val.get("type") == "literal":
                lat, lon = parse_wkt_point(centroid_val["value"])
                if elem_type == "node":
                    elem["lat"] = lat
                    elem["lon"] = lon
                else:
                    elem["center"] = {"lat": lat, "lon": lon}

        # ids/tags + bb: element's own WKT → lat/lon (node) or bounds (way/relation)
        if bb_via_wkt:
            bb_wkt_val = binding.get("bb_wkt")
            if bb_wkt_val and bb_wkt_val.get("type") == "literal":
                wkt_str = bb_wkt_val["value"]
                if wkt_str.startswith("POINT("):
                    lat, lon = parse_wkt_point(wkt_str)
                    elem["lat"] = lat
                    elem["lon"] = lon
                else:
                    coords = parse_wkt_coords(wkt_str)
                    for lat, lon in coords:
                        _update_bounds(elem["_bounds_acc"], lat, lon)

    return [_finalize(elem, stmt) for elem in accum.values()]


def _extract_meta(elem: dict[str, Any], binding: dict[str, Any]) -> None:
    found_any = False
    for field in _META_FIELDS:
        field_val = binding.get(field, {})
        if field == "changeset" and field_val.get("type") == "uri":
            uri = field_val["value"]
            if "/changeset/" in uri:
                elem[field] = int(uri.split("/changeset/")[1])
                found_any = True
        elif field_val.get("type") == "literal":
            value = field_val["value"]
            if field == "timestamp":
                elem[field] = value + "Z"
            elif field in ("version", "uid"):
                elem[field] = int(value)
            else:
                elem[field] = value
            found_any = True
    if found_any:
        elem["_meta_done"] = True


def _finalize(elem: dict[str, Any], stmt: OutStatement) -> dict[str, Any]:
    """Convert an accumulated element into the final Overpass element shape."""
    out: dict[str, Any] = {"type": elem["type"], "id": elem["id"]}
    elem_type = elem["type"]

    # lat/lon (nodes, or any element with center in ids/center mode)
    if "lat" in elem:
        out["lat"] = elem["lat"]
        out["lon"] = elem["lon"]

    # Structural members
    if "_members" in elem:
        members_sorted = sorted(elem["_members"], key=lambda x: x[0])
        geom = elem.get("_geom", {})

        if elem_type == "way":
            out["nodes"] = [ref for _, _, ref, _ in members_sorted]
            if stmt.geom:
                out["geometry"] = [
                    {"lat": lat, "lon": lon}
                    for lat, lon in elem.get("_way_geom", [])
                ]
        elif elem_type == "relation":
            rel_members: list[dict[str, Any]] = []
            for pos, mtype, mref, role in members_sorted:
                member_out: dict[str, Any] = {"type": mtype, "ref": mref, "role": role}
                if stmt.geom:
                    coords = geom.get(pos, [])
                    if coords and mtype == "node":
                        member_out["lat"] = coords[0][0]
                        member_out["lon"] = coords[0][1]
                    elif coords and mtype == "way":
                        member_out["geometry"] = [
                            {"lat": lat, "lon": lon} for lat, lon in coords
                        ]
                rel_members.append(member_out)
            out["members"] = rel_members

    # Tags
    if "tags" in elem:
        out["tags"] = elem["tags"]

    # Meta
    for field in _META_FIELDS:
        if field in elem:
            out[field] = elem[field]

    # Bounds (geom or bb, ways/relations only)
    if "_bounds_acc" in elem:
        acc = elem["_bounds_acc"]
        if acc[0] != math.inf:
            out["bounds"] = _bounds_dict(acc)

    # Center (ways/relations only; nodes use lat/lon inline)
    if "center" in elem:
        out["center"] = elem["center"]

    return out
