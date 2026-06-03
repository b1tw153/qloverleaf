from qloverleaf.composer import _substitute_variable
from qloverleaf.evaluators import translate_evaluator
from qloverleaf.exceptions import (
    QueryError,
    UnimplementedFeatureError,
    UnsupportedFeatureError,
)
from qloverleaf.transformer import (
    _AREA,
    _NODE,
    _NW,
    _NWR,
    _RELATION,
    _WAY,
    _WR,
    AreaIdFilter,
    AreaSetFilter,
    AroundLineFilter,
    AroundPointFilter,
    AroundSetFilter,
    BboxFilter,
    CompleteStatement,
    DifferenceStatement,
    ElementType,
    ForeachStatement,
    ForStatement,
    IdFilter,
    IfFilter,
    IfStatement,
    IsInStatement,
    ItemStatement,
    MapToAreaStatement,
    NewerFilter,
    OutStatement,
    OutVerbosity,
    PivotFilter,
    PolygonFilter,
    QueryFilter,
    QueryStatement,
    RecurseDir,
    RecurseFilter,
    RecurseFilterType,
    RecurseStatement,
    SetFilter,
    SetReference,
    Statement,
    TagFilterOp,
    TagKeyFilter,
    TagValueFilter,
    UidFilter,
    UnionStatement,
    UserFilter,
    WayCountFilter,
)
from qloverleaf.types import SetInjection, SetState, SparqlPattern


def _dump_sparql_pattern(pattern: SparqlPattern) -> str:
    # TODO: add a _dump_statement helper to transformer.py and use it to dump the list
    # of statements
    output_set_str = (
        f".{pattern.output_set.name} (v{pattern.output_set.version})"
        if pattern.output_set
        else "None"
    )
    lines = [
        f"output_set: {output_set_str}",
        f"result_variable: {pattern.result_variable}",
        f"distinct: {pattern.distinct}",
        f"materialize: {pattern.materialize}",
        f"prefixes: {sorted(pattern.prefixes)}",
        "where_clauses:",
    ]
    for clause in pattern.where_clauses:
        lines.append(f"  {clause}")
    lines.append("injections:")
    for inj in pattern.injections:
        lines.append(f"  {inj.sparql_var} <- {inj.set_name}")
    lines.append("")
    return "\n".join(lines)


def _sparql_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


SPARQL_PREFIXES: dict[str, str] = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "osm": "https://www.openstreetmap.org/",
    "osmkey": "https://www.openstreetmap.org/wiki/Key:",
    "osmn": "http://www.openstreetmap.org/node/",
    "osmnode": "https://www.openstreetmap.org/node/",
    "osmway": "https://www.openstreetmap.org/way/",
    "osmrel": "https://www.openstreetmap.org/relation/",
    "osmeta": "https://www.openstreetmap.org/meta/",
    "geo": "http://www.opengis.net/ont/geosparql#",
    "geof": "http://www.opengis.net/def/function/geosparql/",
    "ogc": "http://www.opengis.net/rdf#",
    "osm2rdf": "https://osm2rdf.cs.uni-freiburg.de/rdf#",
}


def render_query(pattern: SparqlPattern, set_state: "SetState") -> str:
    lines: list[str] = []

    for prefix in sorted(pattern.prefixes):
        uri = SPARQL_PREFIXES[prefix]
        lines.append(f"PREFIX {prefix}: <{uri}>")

    # SELECT clause
    if pattern.select_clause:
        clause = pattern.select_clause
        if pattern.distinct and "DISTINCT" not in clause:
            distinct = "DISTINCT "
        else:
            distinct = ""
        lines.append(f"SELECT {distinct}{clause} WHERE {{")
    else:
        assert pattern.result_variable is not None, (
            "Pattern must have output_set or explicit select_clause"
        )
        distinct = "DISTINCT " if pattern.distinct else ""
        lines.append(f"SELECT {distinct}{pattern.result_variable} WHERE {{")

    # VALUES injections
    # site_substitutions maps placeholder strings to their filled VALUES clauses;
    # applied to where_clauses strings after top-level VALUES are emitted
    site_substitutions: dict[str, str] = {}
    for injection in pattern.injections:
        entry = set_state.get(injection.set_name)
        uris: list[tuple[ElementType, str]] = []
        if entry:
            assert (entry.nwr_results is not None) != (
                entry.area_results is not None
            ), "Expected exactly one of nwr_results or area_results to be present"
            if injection.required_types is None or injection.required_types & _AREA:
                uris += entry.area_results or []
            if injection.required_types is None or injection.required_types & _NWR:
                nwr = entry.nwr_results or []
                rt = injection.required_types
                if rt is not None and rt & _NWR and rt & _NWR != _NWR:
                    # required_types is a strict subset of NWR — trim hot injections
                    # to matching types only (performance; cold queries rely on
                    # in-clause type guards for correctness)
                    uris += [(t, u) for t, u in nwr if t in rt]
                else:
                    uris += nwr
        uri_list = " ".join(f"<{u}>" for _, u in uris)
        filled = f"VALUES {injection.sparql_var} {{ {uri_list} }}"
        if injection.marker is not None:
            # Site injection: substitute marker inside where_clauses
            site_substitutions[injection.marker] = filled
        else:
            # Top-level injection: emit VALUES before where_clauses
            lines.append(f"  {filled}")
            # Also substitute any matching placeholder in subqueries
            # (QLever cannot see outer VALUES inside subqueries)
            site_substitutions[f"VALUES {injection.sparql_var} {{ }}"] = filled

    # WHERE clauses — apply site substitutions where needed
    for clause in pattern.where_clauses:
        for placeholder, replacement in site_substitutions.items():
            clause = clause.replace(placeholder, replacement)
        lines.append(f"  {clause}")

    lines.append("}")

    # GROUP BY
    if pattern.group_by:
        lines.append(f"GROUP BY {pattern.group_by}")

    # ORDER BY
    if pattern.order_by:
        lines.append(f"ORDER BY {pattern.order_by}")

    # LIMIT
    if pattern.limit is not None:
        lines.append(f"LIMIT {pattern.limit}")

    return "\n".join(lines)


def _variable_name(
    set_ref: SetReference,
    filter_index: int | None = None,
    intermediate: str | None = None,
) -> str:
    base = f"?{set_ref.identifier}"
    if filter_index is not None:
        base += f"·f{filter_index}"
    if intermediate is not None:
        base += f"·{intermediate}"
    return base


_OSM_TYPE_NAMES: dict[ElementType, str] = {
    ElementType.NODE: "node",
    ElementType.WAY: "way",
    ElementType.RELATION: "relation",
}
_OSM_TYPE_PREFIXES: dict[ElementType, str] = {
    ElementType.NODE: "osmnode",
    ElementType.WAY: "osmway",
    ElementType.RELATION: "osmrel",
}
# Canonical ordering for multi-type UNION clauses and VALUES expansions.
_OSM_TYPE_ORDER = [ElementType.NODE, ElementType.WAY, ElementType.RELATION]


def translate(statement: Statement) -> list[SparqlPattern]:
    output_set: SetReference | None = getattr(statement, "output_set", None)
    if output_set is not None:
        content_types = output_set.content_types
        assert content_types is not None
        assert not (content_types & _NWR and content_types & _AREA), (
            "Cannot translate a statement with mixed output types to a Sparql pattern: "
            f"{content_types}"
        )  # see area-handling.md
    if isinstance(statement, QueryStatement):
        patterns = _translate_query(statement)
    elif isinstance(statement, UnionStatement):
        patterns = _translate_union(statement)
    elif isinstance(statement, DifferenceStatement):
        patterns = _translate_difference(statement)
    elif isinstance(statement, ItemStatement):
        patterns = _translate_item(statement)
    elif isinstance(statement, OutStatement):
        patterns = _translate_out(statement)
    elif isinstance(statement, RecurseStatement):
        patterns = _translate_recurse(statement)
    elif isinstance(statement, IsInStatement):
        patterns = _translate_is_in(statement)
    elif isinstance(statement, MapToAreaStatement):
        patterns = _translate_map_to_area(statement)
    elif isinstance(statement, ForeachStatement):
        patterns = _translate_foreach(statement)
    elif isinstance(statement, ForStatement):
        patterns = _translate_for(statement)
    elif isinstance(statement, CompleteStatement):
        patterns = _translate_complete(statement)
    elif isinstance(statement, IfStatement):
        patterns = _translate_if(statement)
    else:
        raise UnsupportedFeatureError(
            f"No translator for {type(statement).__name__}", statement.token
        )
    for pattern in patterns:
        pattern.statements = [statement]
    return patterns


def _translate_query(statement: QueryStatement) -> list[SparqlPattern]:
    output_set = statement.output_set
    pattern = SparqlPattern(output_set=output_set)
    result_variable = pattern.result_variable
    assert result_variable is not None
    _add_type_filter(statement.element_types, result_variable, pattern)
    for filter_index, f in enumerate(statement.filters):
        _add_query_filter(f, output_set, filter_index, result_variable, pattern)
    return [pattern]


def _add_type_filter(
    element_types: frozenset[ElementType],
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    assert pattern.output_set is not None
    if ElementType.AREA in element_types:
        assert element_types == frozenset({ElementType.AREA})
        element_types = frozenset({ElementType.WAY, ElementType.RELATION})
        pattern.prefixes |= {"osm2rdf"}
        area_var = _variable_name(
            pattern.output_set, filter_index=0, intermediate="area"
        )
        pattern.where_clauses.append(f"{result_variable} osm2rdf:area {area_var} .")
    if ElementType.DERIVED in element_types:
        raise UnsupportedFeatureError("derived element queries are not supported", None)
    osm_types = [_OSM_TYPE_NAMES[t] for t in _OSM_TYPE_ORDER if t in element_types]
    pattern.prefixes |= {"rdf", "osm"}
    if len(osm_types) == 1:
        pattern.where_clauses.append(f"{result_variable} rdf:type osm:{osm_types[0]} .")
    elif len(osm_types) == 2:
        union = " UNION ".join(
            f"{{ {result_variable} rdf:type osm:{t} }}" for t in osm_types
        )
        pattern.where_clauses.append(union)
    else:
        type_var = _variable_name(
            pattern.output_set, filter_index=0, intermediate="type"
        )
        pattern.where_clauses.append(f"{result_variable} rdf:type {type_var} .")


def _add_query_filter(
    f: QueryFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    if isinstance(f, TagKeyFilter):
        _translate_tag_key_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, TagValueFilter):
        _translate_tag_value_filter(
            f, output_set, filter_index, result_variable, pattern
        )
    elif isinstance(f, BboxFilter):
        _translate_bbox_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, IdFilter):
        _translate_id_filter(f, output_set, result_variable, pattern)
    elif isinstance(f, AroundSetFilter):
        _translate_around_set_filter(
            f, output_set, filter_index, result_variable, pattern
        )
    elif isinstance(f, AroundPointFilter):
        _translate_around_point_filter(
            f, output_set, filter_index, result_variable, pattern
        )
    elif isinstance(f, AroundLineFilter):
        _translate_around_line_filter(
            f, output_set, filter_index, result_variable, pattern
        )
    elif isinstance(f, PolygonFilter):
        _translate_polygon_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, NewerFilter):
        _translate_newer_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, UserFilter):
        _translate_user_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, UidFilter):
        _translate_uid_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, AreaIdFilter):
        _translate_area_id_filter(f, result_variable, pattern)
    elif isinstance(f, AreaSetFilter):
        _translate_area_set_filter(
            f, output_set, filter_index, result_variable, pattern
        )
    elif isinstance(f, RecurseFilter):
        _translate_recurse_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, WayCountFilter):
        _translate_way_count_filter(
            f, output_set, filter_index, result_variable, pattern
        )
    elif isinstance(f, SetFilter):
        _translate_set_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, PivotFilter):
        _translate_pivot_filter(f, output_set, filter_index, result_variable, pattern)
    elif isinstance(f, IfFilter):
        _translate_if_filter(f, output_set, filter_index, result_variable, pattern)
    else:
        raise UnimplementedFeatureError(
            "query filter translation is not yet implemented", f.token
        )


def _translate_tag_key_filter(
    f: TagKeyFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes.add("osmkey")
    value_var = _variable_name(output_set, filter_index=filter_index, intermediate="v")
    if f.absent:
        pattern.where_clauses.append(
            f"FILTER NOT EXISTS {{ {result_variable} osmkey:{f.key} {value_var} }}"
        )
    else:
        pattern.where_clauses.append(f"{result_variable} osmkey:{f.key} {value_var} .")


def _translate_tag_value_filter(
    f: TagValueFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes.add("osmkey")
    predicate = f"osmkey:{f.key}"
    literal = _sparql_literal(f.value)
    if f.op == TagFilterOp.EQ:
        pattern.where_clauses.append(f"{result_variable} {predicate} {literal} .")
    elif f.op == TagFilterOp.NEQ:
        pattern.where_clauses.append(
            f"FILTER NOT EXISTS {{ {result_variable} {predicate} {literal} }}"
        )
    elif f.op == TagFilterOp.REGEX or f.op == TagFilterOp.NOT_REGEX:
        value_var = _variable_name(
            output_set, filter_index=filter_index, intermediate="v"
        )
        pattern.where_clauses.append(f"{result_variable} {predicate} {value_var} .")
        flags = ', "i"' if f.case_insensitive else ""
        if f.op == TagFilterOp.REGEX:
            pattern.where_clauses.append(
                f"FILTER(REGEX({value_var}, {literal}{flags}))"
            )
        else:
            pattern.where_clauses.append(
                f"FILTER(!REGEX({value_var}, {literal}{flags}))"
            )
    else:  # f.op == TagFilterOp.KEY_REGEX
        value_var = _variable_name(
            output_set, filter_index=filter_index, intermediate="v"
        )
        predicate_var = _variable_name(
            output_set, filter_index=filter_index, intermediate="p"
        )
        pattern.where_clauses.append(f"{result_variable} {predicate_var} {value_var} .")
        flags = ', "i"' if f.case_insensitive else ""
        key_regex = _sparql_literal(SPARQL_PREFIXES["osmkey"] + f.key)
        pattern.where_clauses.append(
            f"FILTER(REGEX(STR({predicate_var}), {key_regex}{flags}))"
        )
        pattern.where_clauses.append(f"FILTER(REGEX({value_var}, {literal}{flags}))")


def _translate_bbox_filter(
    f: BboxFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes |= {"geo", "geof"}
    geom_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="geom"
    )
    wkt_var = _variable_name(output_set, filter_index=filter_index, intermediate="wkt")
    pattern.where_clauses.append(f"{result_variable} geo:hasGeometry {geom_var} .")
    pattern.where_clauses.append(f"{geom_var} geo:asWKT {wkt_var} .")
    # geof:minX/maxX/minY/maxY work for any geometry type, including POINT (nodes)
    pattern.where_clauses.append(
        f"FILTER(geof:minX({wkt_var}) <= {f.east} && geof:maxX({wkt_var}) >= {f.west})"
    )
    pattern.where_clauses.append(
        f"FILTER(geof:minY({wkt_var}) <= {f.north}"
        f" && geof:maxY({wkt_var}) >= {f.south})"
    )


def _translate_id_filter(
    f: IdFilter,
    output_set: SetReference,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    assert f.output_types is not None
    osm_types = [t for t in _OSM_TYPE_ORDER if t in f.output_types]
    for t in osm_types:
        pattern.prefixes.add(_OSM_TYPE_PREFIXES[t])
        if t is ElementType.NODE:
            pattern.prefixes.add("osmn")
    uris: list[str] = []
    for t in osm_types:
        for id_ in f.ids:
            uris.append(f"{_OSM_TYPE_PREFIXES[t]}:{id_}")
            if t is ElementType.NODE:
                # osm2rdf stores untagged nodes under http:// and tagged nodes
                # under https://; emit both forms so the VALUES set matches
                # whichever scheme the node actually lives at.
                uris.append(f"osmn:{id_}")
    pattern.where_clauses.append(f"VALUES {result_variable} {{ {' '.join(uris)} }}")


def _translate_around_set_filter(
    f: AroundSetFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.distinct = True  # Cross-join may produce duplicates
    pattern.prefixes |= {"geo", "geof"}

    # Reference set geometry variables
    ref_var = _variable_name(output_set, filter_index=filter_index, intermediate="ref")
    ref_geom_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="refgeom"
    )
    ref_wkt_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="refwkt"
    )

    # Target geometry variables
    geom_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="geom"
    )
    wkt_var = _variable_name(output_set, filter_index=filter_index, intermediate="wkt")

    # Inject reference set
    assert f.set_reference.required_types is not None
    pattern.injections.append(
        SetInjection(
            sparql_var=ref_var,
            set_name=f.set_reference.identifier,
            required_types=f.set_reference.required_types,
        )
    )

    # Reference geometry
    pattern.where_clauses.append(f"{ref_var} geo:hasGeometry {ref_geom_var} .")
    pattern.where_clauses.append(f"{ref_geom_var} geo:asWKT {ref_wkt_var} .")

    # Target geometry
    pattern.where_clauses.append(f"{result_variable} geo:hasGeometry {geom_var} .")
    pattern.where_clauses.append(f"{geom_var} geo:asWKT {wkt_var} .")

    # Distance filter
    pattern.where_clauses.append(
        f"FILTER(geof:metricDistance({wkt_var}, {ref_wkt_var}) <= {f.radius})"
    )


def _translate_around_point_filter(
    f: AroundPointFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes |= {"geo", "geof"}
    geom_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="geom"
    )
    wkt_var = _variable_name(output_set, filter_index=filter_index, intermediate="wkt")
    pattern.where_clauses.append(f"{result_variable} geo:hasGeometry {geom_var} .")
    pattern.where_clauses.append(f"{geom_var} geo:asWKT {wkt_var} .")
    point_wkt = f'"POINT({f.lon} {f.lat})"^^geo:wktLiteral'
    pattern.where_clauses.append(
        f"FILTER(geof:metricDistance({wkt_var}, {point_wkt}) <= {f.radius})"
    )


def _translate_around_line_filter(
    f: AroundLineFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes |= {"geo", "geof"}
    geom_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="geom"
    )
    wkt_var = _variable_name(output_set, filter_index=filter_index, intermediate="wkt")
    pattern.where_clauses.append(f"{result_variable} geo:hasGeometry {geom_var} .")
    pattern.where_clauses.append(f"{geom_var} geo:asWKT {wkt_var} .")
    coords = ", ".join(f"{pt.lon} {pt.lat}" for pt in f.points)
    linestring_wkt = f'"LINESTRING({coords})"^^geo:wktLiteral'
    pattern.where_clauses.append(
        f"FILTER(geof:metricDistance({wkt_var}, {linestring_wkt}) <= {f.radius})"
    )


def _translate_polygon_filter(
    f: PolygonFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    assert f.output_types is not None
    pattern.prefixes |= {"geo", "geof"}
    poly_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="poly"
    )
    geom_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="geom"
    )
    wkt_var = _variable_name(output_set, filter_index=filter_index, intermediate="wkt")
    coords = ", ".join(f"{pt.lon} {pt.lat}" for pt in f.points)
    first_pt = f.points[0]
    closed_coords = f"{coords}, {first_pt.lon} {first_pt.lat}"
    polygon_wkt = f'"POLYGON(({closed_coords}))"^^geo:wktLiteral'
    pattern.where_clauses.append(f"VALUES {poly_var} {{ {polygon_wkt} }}")
    pattern.where_clauses.append(f"{result_variable} geo:hasGeometry {geom_var} .")
    pattern.where_clauses.append(f"{geom_var} geo:asWKT {wkt_var} .")
    if f.output_types == {ElementType.NODE}:
        spatial_fn = "geof:sfWithin"
    else:
        spatial_fn = "geof:sfIntersects"
    pattern.where_clauses.append(f"FILTER({spatial_fn}({wkt_var}, {poly_var}))")


def _translate_newer_filter(
    f: NewerFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes |= {"osmeta", "xsd"}
    timestamp_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="ts"
    )
    pattern.where_clauses.append(
        f"{result_variable} osmeta:timestamp {timestamp_var} ."
    )
    datetime_str = f.timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    pattern.where_clauses.append(
        f'FILTER({timestamp_var} > "{datetime_str}"^^xsd:dateTime)'
    )


def _translate_user_filter(
    f: UserFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes.add("osmeta")
    if len(f.users) == 1:
        user_literal = _sparql_literal(f.users[0])
        pattern.where_clauses.append(f"{result_variable} osmeta:user {user_literal} .")
    else:
        user_var = _variable_name(
            output_set, filter_index=filter_index, intermediate="u"
        )
        user_literals = " ".join(_sparql_literal(u) for u in f.users)
        pattern.where_clauses.append(f"VALUES {user_var} {{ {user_literals} }}")
        pattern.where_clauses.append(f"{result_variable} osmeta:user {user_var} .")


def _translate_uid_filter(
    f: UidFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes |= {"osmeta", "xsd"}
    if len(f.uids) == 1:
        pattern.where_clauses.append(
            f'{result_variable} osmeta:uid "{f.uids[0]}"^^xsd:int .'
        )
    else:
        uid_var = _variable_name(
            output_set, filter_index=filter_index, intermediate="uid"
        )
        uid_literals = " ".join(f'"{uid}"^^xsd:int' for uid in f.uids)
        pattern.where_clauses.append(f"VALUES {uid_var} {{ {uid_literals} }}")
        pattern.where_clauses.append(f"{result_variable} osmeta:uid {uid_var} .")


def _translate_area_id_filter(
    f: AreaIdFilter,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes.add("ogc")
    AREA_RELATION_OFFSET = 3_600_000_000
    AREA_WAY_OFFSET = 2_400_000_000
    if f.area_id >= AREA_RELATION_OFFSET:
        relation_id = f.area_id - AREA_RELATION_OFFSET
        pattern.prefixes.add("osmrel")
        area_uri = f"osmrel:{relation_id}"
    elif f.area_id >= AREA_WAY_OFFSET:
        way_id = f.area_id - AREA_WAY_OFFSET
        pattern.prefixes.add("osmway")
        area_uri = f"osmway:{way_id}"
    else:
        raise ValueError(f"Invalid area_id {f.area_id}: must be >= {AREA_WAY_OFFSET}")
    # sfIntersects for ways (matches Overpass semantics); sfContains for nodes/relations
    if f.output_types and ElementType.WAY in f.output_types:
        predicate = "ogc:sfIntersects"
    else:
        predicate = "ogc:sfContains"
    pattern.where_clauses.append(f"{area_uri} {predicate} {result_variable} .")


def _translate_area_set_filter(
    f: AreaSetFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.prefixes.add("ogc")
    area_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="area"
    )
    assert f.set_reference.required_types is not None
    pattern.injections.append(
        SetInjection(
            sparql_var=area_var,
            set_name=f.set_reference.identifier,
            required_types=f.set_reference.required_types,
        )
    )
    # sfIntersects for ways (matches Overpass semantics); sfContains for nodes/relations
    if f.output_types and ElementType.WAY in f.output_types:
        # TODO: Maybe this should always be sfIntersects
        predicate = "ogc:sfIntersects"
    else:
        predicate = "ogc:sfContains"
    pattern.where_clauses.append(f"{area_var} {predicate} {result_variable} .")


def _translate_recurse_filter(
    f: RecurseFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.distinct = True
    input_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="input"
    )

    assert f.set_reference.required_types is not None
    pattern.injections.append(
        SetInjection(
            sparql_var=input_var,
            set_name=f.set_reference.identifier,
            required_types=f.set_reference.required_types,
        )
    )

    match f.recurse_type:
        case RecurseFilterType.W:
            # way → nodes (downward)
            pattern.prefixes.add("osmway")
            pattern.where_clauses.append(
                f"{input_var} osmway:member/osmway:member_id {result_variable} ."
            )

        case RecurseFilterType.R:
            # relation → members (downward)
            pattern.prefixes.add("osmrel")
            if f.role is not None:
                # blank node needed to attach the role filter
                blank_var = _variable_name(
                    output_set, filter_index=filter_index, intermediate="m"
                )
                pattern.where_clauses.append(f"{input_var} osmrel:member {blank_var} .")
                pattern.where_clauses.append(
                    f"{blank_var} osmrel:member_id {result_variable} ."
                )
                pattern.where_clauses.append(
                    f"{blank_var} osmrel:member_role {_sparql_literal(f.role)} ."
                )
            else:
                pattern.where_clauses.append(
                    f"{input_var} osmrel:member/osmrel:member_id {result_variable} ."
                )

        case RecurseFilterType.BN:
            # node → parent ways and/or relations (upward).
            # Uses reverse property paths for the membership lookup
            # (?result osmway:member/osmway:member_id ?input) rather than
            # explicit blank-node triples. The prior query returns the correct
            # URI scheme for each node (http:// for untagged, https:// for
            # tagged), so no dual-scheme handling is needed here.
            #
            # The input VALUES must live inside each UNION leaf (QLever does not push
            # an outer VALUES through UNION). The marker mechanism fills every leaf from
            # the same injection at render time.
            pattern.prefixes.update({"osm", "rdf", "osmway", "osmrel"})
            input_values_marker = f"VALUES {input_var} {{ }}"
            pattern.injections[-1].marker = input_values_marker
            assert f.set_reference.content_types is not None
            # If the source set is mixed (contains ways or relations alongside nodes),
            # pin the input variable to nodes so only the node members are followed.
            if len(f.set_reference.content_types & _WR) > 0:
                input_type = f"{input_var} rdf:type osm:node ."
            else:
                input_type = ""

            def _leaf(*lines: str) -> str:
                return "{ " + " ".join(lines) + " }"

            way_leaf = _leaf(
                input_values_marker,
                input_type,
                f"{result_variable} osmway:member/osmway:member_id {input_var} .",
            )
            rel_leaf = _leaf(
                input_values_marker,
                input_type,
                f"{result_variable} osmrel:member/osmrel:member_id {input_var} .",
            )
            pattern.where_clauses.append(f"{{ {way_leaf} UNION {rel_leaf} }}")

        case RecurseFilterType.BW | RecurseFilterType.BR:
            # way or relation → parent relations (upward).
            # Both produce identical triple patterns; the distinction is in the
            # input URI prefix (osmway: vs osmrel:), which comes from the input set.
            pattern.prefixes.add("osmrel")
            pattern.where_clauses.append(
                f"{result_variable} osmrel:member/osmrel:member_id {input_var} ."
            )


def _translate_way_count_filter(
    f: WayCountFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.distinct = True
    pattern.prefixes.add("osmway")

    way_var = _variable_name(output_set, filter_index=filter_index, intermediate="way")
    count_var = _variable_name(
        output_set, filter_index=filter_index, intermediate="cnt"
    )

    # Inject the input way set - must be materialized due to subquery
    assert f.set_reference.required_types is not None
    pattern.injections.append(
        SetInjection(
            sparql_var=way_var,
            set_name=f.set_reference.identifier,
            required_types=f.set_reference.required_types,
            must_materialize=True,  # Subquery requires VALUES in both locations
        )
    )

    # Join ways to their member nodes (outer query) via blank node
    blank_var = _variable_name(output_set, filter_index=filter_index, intermediate="m")
    pattern.where_clauses.append(f"{way_var} osmway:member {blank_var} .")
    pattern.where_clauses.append(f"{blank_var} osmway:member_id {result_variable} .")

    # Subquery to count how many ways each node appears in
    # Note: VALUES must appear in both outer and inner query due to QLever limitation
    subquery = (
        f"{{ SELECT {result_variable} (COUNT(DISTINCT {way_var}) AS {count_var})"
        " WHERE {"
        f" VALUES {way_var} {{ }}"
        f" {way_var} osmway:member {blank_var} ."
        f" {blank_var} osmway:member_id {result_variable} ."
        f" }} GROUP BY {result_variable} }}"
    )
    pattern.where_clauses.append(subquery)

    # Add FILTER based on count constraints
    if f.exact:
        pattern.where_clauses.append(f"FILTER({count_var} = {f.min_count})")
    elif f.max_count is None:
        # Open upper bound (N-)
        pattern.where_clauses.append(f"FILTER({count_var} >= {f.min_count})")
    else:
        # Range (min-max)
        pattern.where_clauses.append(
            f"FILTER({count_var} >= {f.min_count} && {count_var} <= {f.max_count})"
        )


def _translate_set_filter(
    f: SetFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    pattern.injections.append(
        SetInjection(
            sparql_var=result_variable,
            set_name=f.set_reference.identifier,
            required_types=f.set_reference.required_types,
        )
    )


def _translate_pivot_filter(
    f: PivotFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    # pivot is a no-op in QLever - areas are already the source ways/relations
    # This behaves identically to SetFilter: inject the input set as VALUES
    assert f.set_reference.required_types is not None
    pattern.injections.append(
        SetInjection(
            sparql_var=result_variable,
            set_name=f.set_reference.identifier,
            required_types=f.set_reference.required_types,
        )
    )


def _translate_if_filter(
    f: IfFilter,
    output_set: SetReference,
    filter_index: int,
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    variable_base = _variable_name(output_set, filter_index=filter_index)
    evaluator_pattern = translate_evaluator(f.evaluator, result_variable, variable_base)
    if evaluator_pattern.subqueries:
        raise UnimplementedFeatureError(
            "evaluator subqueries in if filters are not yet implemented", f.token
        )
    pattern.prefixes |= evaluator_pattern.prefixes
    pattern.where_clauses.extend(evaluator_pattern.clauses)
    pattern.where_clauses.append(f"FILTER({evaluator_pattern.expression})")


def _translate_union(stmt: UnionStatement) -> list[SparqlPattern]:
    output_set = stmt.output_set
    result_variable = f"?{output_set.identifier}"
    pattern = SparqlPattern(output_set=output_set, distinct=True)

    leaves: list[str] = []
    # In OverpassQL, ._ propagates sequentially between union members, so a later
    # member (e.g. >) can read from the output of the member before it.  Maps each
    # processed member's output_set.identifier → its pattern so those dependencies
    # can be inlined rather than lifted as external set_state lookups.
    member_outputs: dict[str, SparqlPattern] = {}

    for leaf_idx, member in enumerate(stmt.members):
        if isinstance(
            member,
            (
                OutStatement,
                ForeachStatement,
                ForStatement,
                IfStatement,
                CompleteStatement,
            ),
        ):
            raise QueryError(
                f"{type(member).__name__} cannot appear"
                " as a member of a union statement",
                member.token,
            )

        member_patterns = translate(member)
        if len(member_patterns) != 1:
            raise UnimplementedFeatureError(
                "hot pipeline members in UnionStatement are not yet supported",
                member.token,
            )
        mp = member_patterns[0]

        if mp.materialize:
            raise UnimplementedFeatureError(
                "hot pipeline members in UnionStatement are not yet supported",
                member.token,
            )
        if mp.select_clause or mp.group_by or mp.order_by or mp.limit is not None:
            raise UnimplementedFeatureError(
                "output-stage members in UnionStatement are not yet supported",
                member.token,
            )
        if any(inj.must_materialize for inj in mp.injections):
            raise UnimplementedFeatureError(
                "hot set injections (e.g. way_count filter) in UnionStatement"
                " are not yet supported",
                member.token,
            )

        old_var = mp.result_variable
        assert old_var is not None

        # Substitute the member's result variable → union's result variable in clauses.
        # Intermediate variables (e.g. ?way1·f0·geom) are not matched because · follows
        # the identifier and the regex lookahead excludes it.
        leaf_clauses = [
            _substitute_variable(clause, old_var, result_variable)
            for clause in mp.where_clauses
        ]
        pattern.prefixes |= mp.prefixes

        # Every injection from a member must become a site injection inside its leaf.
        # QLever evaluates each UNION branch independently so an outer VALUES is not
        # visible inside a branch; the constraint must live in the leaf.
        for inj in mp.injections:
            new_sparql_var = _substitute_variable(
                inj.sparql_var, old_var, result_variable
            )

            if inj.set_name in member_outputs:
                # Intra-union pipeline: reads from a previous member's output.
                # That result is already folded into a UNION leaf and never stored
                # in set_state, so the previous member's WHERE clauses must be
                # inlined directly to keep each UNION branch self-contained.
                prev_mp = member_outputs[inj.set_name]
                prev_old_var = prev_mp.result_variable
                assert prev_old_var is not None
                pattern.prefixes |= prev_mp.prefixes

                if inj.marker is not None and prev_mp.where_clauses:
                    # Site injection, prev has WHERE clauses: inline in place of marker.
                    # Rename prev result variable → this injection's input variable.
                    inline_clauses = [
                        _substitute_variable(c, prev_old_var, new_sparql_var)
                        for c in prev_mp.where_clauses
                    ]
                    leaf_clauses = [
                        c.replace(inj.marker, "\n  ".join(inline_clauses))
                        for c in leaf_clauses
                    ]
                    # Lift external injections whose markers are now in the inlined text
                    for prev_inj in prev_mp.injections:
                        pattern.injections.append(
                            SetInjection(
                                sparql_var=prev_inj.sparql_var,
                                set_name=prev_inj.set_name,
                                required_types=prev_inj.required_types,
                                must_materialize=prev_inj.must_materialize,
                                marker=prev_inj.marker,
                            )
                        )

                elif inj.marker is not None:
                    # Site injection, prev has no WHERE clauses: pass-through
                    # (e.g. item statement ._).  The previous member is a pure alias
                    # from its injected source.  We cannot inline empty clauses here:
                    # that would replace the marker with nothing (destroying the
                    # constraint), and lifting the flat alias injection would append
                    # its clauses to the outer WHERE rather than inside the branch.
                    # Instead, re-point the current site marker to the source set.
                    for prev_inj in prev_mp.injections:
                        if prev_inj.marker is None:
                            # Flat source: bind current marker to the upstream set.
                            # Use this injection's sparql_var and required_types —
                            # prev_inj's name the alias variable, not the right var.
                            pattern.injections.append(
                                SetInjection(
                                    sparql_var=new_sparql_var,
                                    set_name=prev_inj.set_name,
                                    required_types=inj.required_types,
                                    must_materialize=prev_inj.must_materialize,
                                    marker=inj.marker,
                                )
                            )
                        else:
                            # Site source: lift as-is (marker is already in the leaf)
                            pattern.injections.append(
                                SetInjection(
                                    sparql_var=prev_inj.sparql_var,
                                    set_name=prev_inj.set_name,
                                    required_types=prev_inj.required_types,
                                    must_materialize=prev_inj.must_materialize,
                                    marker=prev_inj.marker,
                                )
                            )

                elif prev_mp.where_clauses:
                    # Flat injection, prev has WHERE clauses: arises when an item
                    # statement (._) follows a member that has WHERE clauses, e.g.
                    # ( >; ._; ).  Item statements produce flat injections (no site
                    # marker), so there is no placeholder to replace in the leaf.
                    # Instead, prepend the previous member's WHERE clauses directly.
                    # Intermediate variables (e.g. ?_2·ir) must be renamed with a
                    # leaf-specific suffix so their marker strings are unique — the
                    # composer fills each marker exactly once, and the same marker
                    # text in two UNION branches would leave the second one unfilled.
                    renamed_clauses = list(prev_mp.where_clauses)
                    renamed_prev_injections: list[SetInjection] = []
                    for prev_inj in prev_mp.injections:
                        if prev_inj.marker is None:
                            raise UnimplementedFeatureError(
                                "flat injection in flat intra-union"
                                " pipeline is not yet supported",
                                member.token,
                            )
                        old_ivar = prev_inj.sparql_var
                        new_ivar = f"{old_ivar}·l{leaf_idx}"
                        renamed_clauses = [
                            _substitute_variable(c, old_ivar, new_ivar)
                            for c in renamed_clauses
                        ]
                        renamed_prev_injections.append(
                            SetInjection(
                                sparql_var=new_ivar,
                                set_name=prev_inj.set_name,
                                required_types=prev_inj.required_types,
                                must_materialize=prev_inj.must_materialize,
                                marker=_substitute_variable(
                                    prev_inj.marker, old_ivar, new_ivar
                                ),
                            )
                        )
                    inline_clauses = [
                        _substitute_variable(c, prev_old_var, new_sparql_var)
                        for c in renamed_clauses
                    ]
                    leaf_clauses = inline_clauses + leaf_clauses
                    for renamed_inj in renamed_prev_injections:
                        pattern.injections.append(renamed_inj)

                else:
                    raise UnimplementedFeatureError(
                        "chained pass-through in flat intra-union"
                        " pipeline is not yet supported",
                        member.token,
                    )

            elif inj.marker is not None:
                # Already a site injection: the marker is embedded in leaf_clauses via
                # the intermediate variable name, which is unique across members and
                # does not change (· prevents substitution above).
                pattern.injections.append(
                    SetInjection(
                        sparql_var=new_sparql_var,
                        set_name=inj.set_name,
                        required_types=inj.required_types,
                        must_materialize=inj.must_materialize,
                        marker=inj.marker,
                    )
                )

            else:
                # Flat injection: create a leaf-specific marker and insert it first so
                # QLever sees the binding before evaluating subsequent triple patterns.
                new_marker = f"VALUES {new_sparql_var}·u{leaf_idx} {{ }}"
                leaf_clauses.insert(0, new_marker)
                pattern.injections.append(
                    SetInjection(
                        sparql_var=new_sparql_var,
                        set_name=inj.set_name,
                        required_types=inj.required_types,
                        must_materialize=inj.must_materialize,
                        marker=new_marker,
                    )
                )

        assert mp.output_set is not None  # all union members write to an output set
        member_outputs[mp.output_set.identifier] = mp
        leaves.append("{\n  " + "\n  ".join(leaf_clauses) + "\n}")

    if not leaves:
        # Empty union ( ) always produces an empty set
        pattern.where_clauses.append(f"VALUES {result_variable} {{ }}")
        return [pattern]

    pattern.where_clauses.append("\nUNION\n".join(leaves))
    return [pattern]


def _translate_difference(stmt: DifferenceStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "DifferenceStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_item(stmt: ItemStatement) -> list[SparqlPattern]:
    # ItemStatement just maps the input set to the output set
    pattern = SparqlPattern(output_set=stmt.output_set)
    sparql_var = pattern.result_variable
    assert sparql_var is not None

    # Inject the input set and assign to the output set variable
    pattern.injections = [
        SetInjection(
            sparql_var=sparql_var,
            set_name=stmt.input_set.identifier,
            required_types=stmt.input_set.required_types,
        )
    ]
    return [pattern]


_BRANCH_SUFFIX: dict[ElementType, str] = {
    ElementType.NODE: "",
    ElementType.WAY: "·way",
    ElementType.RELATION: "·rel",
}


def _injection_marker(sparql_var: str, elem_type: ElementType) -> str:
    """Unique injection site marker for one branch of a type UNION block."""
    return f"VALUES {sparql_var}{_BRANCH_SUFFIX[elem_type]} {{ }}"


def _meta_branch_lines(result_variable: str) -> list[str]:
    return [
        f"{result_variable} osmeta:version ?version .",
        f"{result_variable} osmeta:timestamp ?timestamp .",
        f"{result_variable} osmeta:changeset ?changeset .",
        f"{result_variable} osmeta:uid ?uid .",
        f"{result_variable} osmeta:user ?user .",
    ]


def _node_branch(
    result_variable: str,
    marker: str,
    multiple_types: bool,
    include_meta: bool,
) -> tuple[list[str], list[str]]:
    lines = [f"{result_variable} rdf:type osm:node ."] if multiple_types else []
    lines.extend(
        [
            marker,
            f"{result_variable} geo:hasGeometry/geo:asWKT ?wkt .",
        ]
    )
    if include_meta:
        lines.extend(_meta_branch_lines(result_variable))
    return lines, ["?wkt"]


def _way_branch(
    result_variable: str,
    marker: str,
    multiple_types: bool,
    include_meta: bool,
) -> tuple[list[str], list[str]]:
    lines = [f"{result_variable} rdf:type osm:way ."] if multiple_types else []
    lines.extend(
        [
            marker,
            f"{result_variable} osmway:member ?m .",
            "?m osmway:member_id ?member .",
            "?m osmway:member_pos ?pos .",
        ]
    )
    if include_meta:
        lines.extend(_meta_branch_lines(result_variable))
    return lines, ["?member", "?pos"]


def _relation_branch(
    result_variable: str,
    marker: str,
    multiple_types: bool,
    include_meta: bool,
    include_member_wkt: bool,
) -> tuple[list[str], list[str]]:
    lines = [f"{result_variable} rdf:type osm:relation ."] if multiple_types else []
    lines.extend(
        [
            marker,
            f"{result_variable} osmrel:member ?m .",
            "?m osmrel:member_id ?member .",
            "?m osmrel:member_pos ?pos .",
            "?m osmrel:member_role ?role .",
        ]
    )
    if include_meta:
        lines.extend(_meta_branch_lines(result_variable))
    new_vars = ["?member", "?pos", "?role"]
    if include_member_wkt:
        # Per-member WKT: POINT for node members, LINESTRING/POLYGON for way
        # members, unbound for sub-relation members. Must come after
        # `?m osmrel:member_id ?member` so ?member is bound — otherwise
        # QLever full-scans geo:hasGeometry.
        lines.extend(
            [
                "?member geo:hasGeometry/geo:asWKT ?wkt .",
            ]
        )
        new_vars.append("?wkt")
    return lines, new_vars


def _build_skel_body_meta_pattern(
    stmt: OutStatement,
    pattern: SparqlPattern,
    input_set: SetReference,
    result_variable: str,
    required_types: frozenset[ElementType],
) -> None:
    """Build the SPARQL pattern for skel/body/meta verbosities.

    Nodes get geometry; ways/relations get ordered member lists. Body adds a
    UNION branch for tags — each row is either a skel row or a tag row, never
    both, and the formatter combines them per element. Meta adds flat osmeta:
    triples inside each type branch. All three use one branch per element type
    with an injection marker so cold clauses land inside the branch (Option 2)
    and hot sets get type-filtered VALUES inside the branch (Option 1).
    """
    include_tags = stmt.verbosity in (OutVerbosity.BODY, OutVerbosity.META)
    include_meta = stmt.verbosity == OutVerbosity.META
    # bb/center/geom reuse the per-member-WKT collection path: bounds and center
    # are derived from the union of member coordinates in the formatter. For
    # nodes the element's own ?wkt POINT from the NODE branch is sufficient.
    include_member_wkt = stmt.geom or stmt.bb or stmt.center
    pattern.prefixes |= {"rdf", "osm", "osmway", "osmrel", "geo"}
    if include_tags:
        pattern.prefixes.add("osmkey")
    if include_meta:
        pattern.prefixes.add("osmeta")
    select_parts = [result_variable]
    branches: list[str] = []
    has_members = False

    assert input_set.content_types is not None
    multiple_types = len(input_set.content_types) > 1

    for elem_type in _OSM_TYPE_ORDER:
        if elem_type not in input_set.content_types:
            continue
        marker = _injection_marker(result_variable, elem_type)

        if elem_type == ElementType.NODE:
            branch_lines, new_vars = _node_branch(
                result_variable, marker, multiple_types, include_meta
            )
        elif elem_type == ElementType.WAY:
            branch_lines, new_vars = _way_branch(
                result_variable, marker, multiple_types, include_meta
            )
            has_members = True
        else:
            branch_lines, new_vars = _relation_branch(
                result_variable,
                marker,
                multiple_types,
                include_meta,
                include_member_wkt,
            )
            has_members = True

        for v in new_vars:
            if v not in select_parts:
                select_parts.append(v)
        branches.append("{\n  " + "\n  ".join(branch_lines) + "\n}")
        pattern.injections.append(
            SetInjection(
                sparql_var=result_variable,
                set_name=input_set.identifier,
                required_types=frozenset({elem_type}),
                marker=marker,
            )
        )

    if include_member_wkt and ElementType.WAY in input_set.content_types:
        way_geom_marker = f"VALUES {result_variable}·way_geom {{ }}"
        way_geom_branch_lines = (
            [f"{result_variable} rdf:type osm:way ."] if multiple_types else []
        )
        way_geom_branch_lines.extend(
            [
                way_geom_marker,
                f"{result_variable} geo:hasGeometry/geo:asWKT ?member_wkt .",
            ]
        )
        if "?member_wkt" not in select_parts:
            select_parts.append("?member_wkt")
        branches.append("{\n  " + "\n  ".join(way_geom_branch_lines) + "\n}")
        pattern.injections.append(
            SetInjection(
                sparql_var=result_variable,
                set_name=input_set.identifier,
                required_types=required_types,
                marker=way_geom_marker,
            )
        )

    if include_tags:
        tags_marker = f"VALUES {result_variable}·tags {{ }}"
        tags_branch_lines = [
            tags_marker,
            f"{result_variable} ?p ?v .",
            'FILTER(STRSTARTS(STR(?p), "https://www.openstreetmap.org/wiki/Key:"))',
        ]
        branches.append("{\n  " + "\n  ".join(tags_branch_lines) + "\n}")
        pattern.injections.append(
            SetInjection(
                sparql_var=result_variable,
                set_name=input_set.identifier,
                required_types=required_types,
                marker=tags_marker,
            )
        )
        for v in ["?p", "?v"]:
            if v not in select_parts:
                select_parts.append(v)

    if include_meta:
        for v in ["?version", "?timestamp", "?changeset", "?uid", "?user"]:
            select_parts.append(v)

    pattern.select_clause = " ".join(select_parts)
    pattern.where_clauses.append("\nUNION\n".join(branches))

    order_by = result_variable
    if has_members:
        order_by += " ?pos"
    pattern.order_by = order_by
    pattern.limit = stmt.limit


def _translate_out(stmt: OutStatement) -> list[SparqlPattern]:
    # OutStatement doesn't produce a set, only outputs an existing one
    pattern = SparqlPattern(output_set=None)

    input_set = stmt.input_set
    result_variable = f"?{input_set.identifier}"
    assert input_set.required_types is not None
    required_types = input_set.required_types

    def _flat_injection() -> SetInjection:
        return SetInjection(
            sparql_var=result_variable,
            set_name=input_set.identifier,
            required_types=required_types,
        )

    if stmt.count:
        # Per-type count breakdown with GROUP BY
        pattern.injections.append(_flat_injection())
        pattern.prefixes |= {"rdf", "osm"}
        pattern.select_clause = f"?type (COUNT(DISTINCT {result_variable}) AS ?count)"
        pattern.group_by = "?type"
        pattern.where_clauses.append(f"{result_variable} rdf:type ?type .")
        # ORDER BY / LIMIT don't apply to count
    elif stmt.verbosity == OutVerbosity.IDS:
        pattern.distinct = True
        if stmt.bb or stmt.center:
            # ids + bb: emit element URIs plus the element's own WKT so the formatter
            # can derive bounds (ways/relations) or lat/lon (nodes). Use a
            # site-injection marker so the input bindings land before geo:hasGeometry;
            # otherwise QLever evaluates `?x geo:hasGeometry ... }` against the unbound
            # ?x and full-scans the dataset.
            # ids + center: emit the same WKT to calculate the bbox center
            pattern.prefixes.add("geo")
            bb_marker = f"VALUES {result_variable} {{ }}"
            pattern.select_clause = f"{result_variable} ?bb_wkt"
            pattern.where_clauses.append(bb_marker)
            pattern.where_clauses.append(
                f"{result_variable} geo:hasGeometry/geo:asWKT ?bb_wkt ."
            )
            pattern.injections.append(
                SetInjection(
                    sparql_var=result_variable,
                    set_name=input_set.identifier,
                    required_types=required_types,
                    marker=bb_marker,
                )
            )
        else:
            pattern.injections.append(_flat_injection())
            pattern.select_clause = result_variable
    elif stmt.verbosity == OutVerbosity.TAGS:
        if stmt.bb or stmt.center:
            # tags + bb: two-branch UNION. Tag rows carry ?p/?v; bb rows carry the
            # element's own ?bb_wkt. Mirrors the body design of separating tag rows
            # from skel rows to avoid repeating WKT on every tag row. Each branch puts
            # its marker first so the input substitution binds ?_1 before the subsequent
            # triple patterns — otherwise QLever full-scans the dataset (?p/?v unbound;
            # geo:hasGeometry unbound).
            # tags + center: same two-branch UNION
            pattern.prefixes.add("geo")
            tags_marker = f"VALUES {result_variable}·tags {{ }}"
            bb_marker = f"VALUES {result_variable}·bb {{ }}"
            tags_branch = (
                "{\n  "
                + tags_marker
                + f"\n  {result_variable} ?p ?v ."
                + "\n  FILTER(STRSTARTS(STR(?p),"
                ' "https://www.openstreetmap.org/wiki/Key:"))\n}'
            )
            bb_branch = (
                "{\n  "
                + bb_marker
                + f"\n  {result_variable} geo:hasGeometry/geo:asWKT ?bb_wkt ."
                + "\n}"
            )
            pattern.select_clause = f"{result_variable} ?p ?v ?bb_wkt"
            pattern.where_clauses.append(tags_branch + "\nUNION\n" + bb_branch)
            pattern.injections.append(
                SetInjection(
                    sparql_var=result_variable,
                    set_name=input_set.identifier,
                    required_types=required_types,
                    marker=tags_marker,
                )
            )
            pattern.injections.append(
                SetInjection(
                    sparql_var=result_variable,
                    set_name=input_set.identifier,
                    required_types=required_types,
                    marker=bb_marker,
                )
            )
        else:
            pattern.injections.append(_flat_injection())
            pattern.select_clause = f"{result_variable} ?p ?v"
            pattern.where_clauses.append(f"{result_variable} ?p ?v .")
            pattern.where_clauses.append(
                'FILTER(STRSTARTS(STR(?p), "https://www.openstreetmap.org/wiki/Key:"))'
            )
    elif stmt.verbosity in (OutVerbosity.SKEL, OutVerbosity.BODY, OutVerbosity.META):
        _build_skel_body_meta_pattern(
            stmt, pattern, input_set, result_variable, required_types
        )
        return [pattern]
    else:
        raise UnimplementedFeatureError(
            f"out {stmt.verbosity.value} not yet implemented",
            stmt.token,
        )

    if not stmt.count:
        pattern.order_by = result_variable
        pattern.limit = stmt.limit

    return [pattern]


def _translate_recurse(stmt: RecurseStatement) -> list[SparqlPattern]:
    pattern = SparqlPattern(output_set=stmt.output_set, distinct=True)
    result_var = f"?{stmt.output_set.identifier}"
    input_set = stmt.input_set
    assert input_set.content_types is not None
    input_types = input_set.content_types
    branches: list[str] = []

    def _leaf(*lines: str) -> str:
        return "{\n  " + "\n  ".join(lines) + "\n}"

    def _add_input_branch(
        ivar: str,
        required_types: frozenset[ElementType],
        *clauses: str,
    ) -> None:
        marker = f"VALUES {ivar} {{ }}"
        pattern.injections.append(
            SetInjection(
                sparql_var=ivar,
                set_name=input_set.identifier,
                required_types=required_types,
                marker=marker,
            )
        )
        branches.append(_leaf(marker, *clauses))

    def _add_passthrough_branch(marker_suffix: str) -> None:
        # Input relations pass through to the output unchanged.
        marker = f"VALUES {result_var}·{marker_suffix} {{ }}"
        pattern.injections.append(
            SetInjection(
                sparql_var=result_var,
                set_name=input_set.identifier,
                required_types=_RELATION,
                marker=marker,
            )
        )
        branches.append(_leaf(marker, f"{result_var} rdf:type osm:relation ."))

    # Intermediate variable names, all scoped to the output set identifier.
    iw = _variable_name(stmt.output_set, intermediate="iw")  # way input
    ir = _variable_name(stmt.output_set, intermediate="ir")  # relation input
    ir2 = _variable_name(stmt.output_set, intermediate="ir2")  # relation (2nd branch)
    inw = _variable_name(stmt.output_set, intermediate="inw")  # node-or-way input
    inn = _variable_name(stmt.output_set, intermediate="in")  # node-only input
    in2 = _variable_name(stmt.output_set, intermediate="in2")  # node-only (2nd branch)
    w = _variable_name(stmt.output_set, intermediate="w")  # way bridge (osmrel↔osmway)

    match stmt.recurse_dir:
        case RecurseDir.DOWN:
            # > expands ways to their member nodes, and relations to their direct
            # node/way members (sub-relations excluded) plus the member nodes of
            # those ways. Nodes contribute nothing.
            pattern.prefixes |= {"osmway", "osmrel", "rdf", "osm"}
            if ElementType.WAY in input_types:
                _add_input_branch(
                    iw,
                    _WAY,
                    f"{iw} osmway:member/osmway:member_id {result_var} .",
                )
            if ElementType.RELATION in input_types:
                # Branch 1: direct node/way members; rdf:type UNION excludes sub-rels
                _add_input_branch(
                    ir,
                    _RELATION,
                    f"{{ {result_var} rdf:type osm:node }}"
                    f" UNION {{ {result_var} rdf:type osm:way }}",
                    f"{ir} osmrel:member/osmrel:member_id {result_var} .",
                )
                # Branch 2: nodes of direct way members (two-hop)
                _add_input_branch(
                    ir2,
                    _RELATION,
                    f"{ir2} osmrel:member/osmrel:member_id {w} .",
                    f"{w} osmway:member/osmway:member_id {result_var} .",
                )

        case RecurseDir.DOWN_RELATIONS:
            # >> recurses through the full relation hierarchy downward.
            # Input relations pass through to the output; the way branch is
            # unchanged from >. Separate osmrel and osmway branches avoid a
            # combined transitive path over osmway:member (~7B triples).
            pattern.prefixes |= {"osmway", "osmrel", "rdf", "osm"}
            if ElementType.RELATION in input_types:
                _add_passthrough_branch("pass")
                _add_input_branch(
                    ir,
                    _RELATION,
                    f"{ir} (osmrel:member/osmrel:member_id)+ {result_var} .",
                )
                # Nodes of descendant ways (transitive path reaches ways at any depth)
                _add_input_branch(
                    ir2,
                    _RELATION,
                    f"{ir2} (osmrel:member/osmrel:member_id)+ {w} .",
                    f"{w} osmway:member/osmway:member_id {result_var} .",
                )
            if ElementType.WAY in input_types:
                _add_input_branch(
                    iw,
                    _WAY,
                    f"{iw} osmway:member/osmway:member_id {result_var} .",
                )

        case RecurseDir.UP:
            # < finds direct containers of elements in the current set.
            # Nodes contribute three branches; ways contribute only the shared branch.
            # Input relations pass through unchanged.
            pattern.prefixes |= {"osmway", "osmrel", "rdf", "osm"}
            if ElementType.NODE in input_types or ElementType.WAY in input_types:
                # Shared: relations directly containing input nodes or ways.
                # rdf:type UNION guards against relation URIs reaching this branch.
                _add_input_branch(
                    inw,
                    input_types & _NW,
                    f"{{ {inw} rdf:type osm:node }} UNION {{ {inw} rdf:type osm:way }}",
                    f"{result_var} osmrel:member/osmrel:member_id {inw} .",
                )
            if ElementType.NODE in input_types:
                # Node-only: parent ways of input nodes
                _add_input_branch(
                    inn,
                    _NODE,
                    f"{result_var} osmway:member/osmway:member_id {inn} .",
                )
                # Node-only: relations containing parent ways (two-hop)
                _add_input_branch(
                    in2,
                    _NODE,
                    f"{result_var} osmrel:member/osmrel:member_id {w} .",
                    f"{w} osmway:member/osmway:member_id {in2} .",
                )
            if ElementType.RELATION in input_types:
                _add_passthrough_branch("pass")

        case RecurseDir.UP_RELATIONS:
            # << recurses through the full relation hierarchy upward. Same branch
            # shapes as <, with single-hop relation lookups replaced by transitive
            # paths. osmrel:member (~161M triples) is feasible for anchored
            # transitive paths; osmway:member (~7B) is kept in its own branch.
            pattern.prefixes |= {"osmway", "osmrel", "rdf", "osm"}

            # Shared: all relation ancestors of input nodes, ways, or relations
            # (transitive).
            _add_input_branch(
                inw,
                input_types & _NWR,
                f"{result_var} (osmrel:member/osmrel:member_id)+ {inw} .",
            )
            if ElementType.NODE in input_types:
                # Node-only: parent ways of input nodes
                _add_input_branch(
                    inn,
                    _NODE,
                    f"{result_var} osmway:member/osmway:member_id {inn} .",
                )
                # Node-only: relation ancestors via parent ways (transitive)
                _add_input_branch(
                    in2,
                    _NODE,
                    f"{w} osmway:member/osmway:member_id {in2} .",
                    f"{result_var} (osmrel:member/osmrel:member_id)+ {w} .",
                )
            if ElementType.RELATION in input_types:
                _add_passthrough_branch("pass")

    pattern.where_clauses.append("\nUNION\n".join(branches))
    return [pattern]


def _translate_is_in(stmt: IsInStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "IsInStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_map_to_area(stmt: MapToAreaStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "MapToAreaStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_foreach(stmt: ForeachStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "ForeachStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_for(stmt: ForStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "ForStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_complete(stmt: CompleteStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "CompleteStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_if(stmt: IfStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "IfStatement translation is not yet implemented",
        stmt.token,
    )
