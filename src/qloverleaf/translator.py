from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from qloverleaf.exceptions import UnimplementedFeatureError, UnsupportedFeatureError

# TODO: Consider refactoring to avoid circular imports
if TYPE_CHECKING:
    from qloverleaf.interpreter import SetState
from qloverleaf.transformer import (
    _AREA,
    _NWR,
    AreaIdFilter,
    AreaSetFilter,
    AroundLineFilter,
    AroundPointFilter,
    AroundSetFilter,
    BboxFilter,
    CompleteStatement,
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


@dataclass
class SetInjection:
    sparql_var: str  # e.g. "?a0"
    set_name: str  # versioned set name to look up in set state, e.g. "a0"
    # required_types specifies what the injection consumes from the set;
    # None means whatever the set contains
    required_types: frozenset[ElementType] | None
    must_materialize: bool = (
        False  # True if this input must be materialized (cannot compose)
    )
    # marker: if set, substitute this placeholder string in where_clauses with
    # VALUES {sparql_var} { uri_list } (hot) or cold clauses (cold), rather
    # than emitting a top-level VALUES block
    marker: str | None = None


@dataclass
class SparqlPattern:
    output_set: SetReference | None
    materialize: bool = False
    output: bool = False
    prefixes: set[str] = field(default_factory=set)
    select_clause: str | None = None
    distinct: bool = False
    group_by: str | None = None
    order_by: str | None = None
    where_clauses: list[str] = field(default_factory=list)
    injections: list[SetInjection] = field(default_factory=list)
    limit: int | None = None

    @property
    def result_variable(self) -> str | None:
        """SPARQL variable name with ? prefix (e.g., '?craters1')"""
        return f"?{self.output_set.identifier}" if self.output_set else None

    @property
    def result_set_name(self) -> str | None:
        """Set state key without ? prefix (e.g., 'craters1')"""
        return self.output_set.identifier if self.output_set else None


def _dump_sparql_pattern(pattern: SparqlPattern) -> str:
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
                uris += entry.nwr_results or []
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
        return _translate_query(statement)
    if isinstance(statement, UnionStatement):
        return _translate_union(statement)
    if isinstance(statement, ItemStatement):
        return _translate_item(statement)
    if isinstance(statement, OutStatement):
        return _translate_out(statement)
    if isinstance(statement, RecurseStatement):
        return _translate_recurse(statement)
    if isinstance(statement, IsInStatement):
        return _translate_is_in(statement)
    if isinstance(statement, MapToAreaStatement):
        return _translate_map_to_area(statement)
    if isinstance(statement, ForeachStatement):
        return _translate_foreach(statement)
    if isinstance(statement, ForStatement):
        return _translate_for(statement)
    if isinstance(statement, CompleteStatement):
        return _translate_complete(statement)
    if isinstance(statement, IfStatement):
        return _translate_if(statement)
    raise UnsupportedFeatureError(
        f"No translator for {type(statement).__name__}", statement.token
    )


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
    if ElementType.AREA in element_types:
        assert element_types == frozenset({ElementType.AREA})
        element_types = frozenset({ElementType.WAY, ElementType.RELATION})
        pattern.prefixes |= {"osm2rdf"}
        assert pattern.output_set is not None
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
    else:
        union = " UNION ".join(
            f"{{ {result_variable} rdf:type osm:{t} }}" for t in osm_types
        )
        pattern.where_clauses.append(union)


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
    else:
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
    uris: list[str] = []
    for t in osm_types:
        for id_ in f.ids:
            uris.append(f"{_OSM_TYPE_PREFIXES[t]}:{id_}")
            if t is ElementType.NODE:
                # osm2rdf stores untagged nodes under http:// and tagged nodes
                # under https://; emit both forms so the VALUES set matches
                # whichever scheme the node actually lives at.
                uris.append(f"<http://www.openstreetmap.org/node/{id_}>")
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
    blank_var = _variable_name(output_set, filter_index=filter_index, intermediate="m")

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
            pattern.where_clauses.append(f"{input_var} osmway:member {blank_var} .")
            pattern.where_clauses.append(
                f"{blank_var} osmway:member_id {result_variable} ."
            )

        case RecurseFilterType.R:
            # relation → members (downward)
            pattern.prefixes.add("osmrel")
            pattern.where_clauses.append(f"{input_var} osmrel:member {blank_var} .")
            pattern.where_clauses.append(
                f"{blank_var} osmrel:member_id {result_variable} ."
            )
            if f.role is not None:
                pattern.where_clauses.append(
                    f'{blank_var} osmrel:member_role "{f.role}" .'
                )

        case RecurseFilterType.BN:
            # node → parent ways and/or relations (upward).
            # osmway:member_id and osmrel:member_id store node URIs using http://
            # for untagged nodes and https:// for tagged nodes. Both schemes must
            # be covered. The input variable carries the https:// form (osmnode:
            # prefix), so we derive the http:// form with BIND inside each leaf
            # that needs it.
            #
            # In QLever each UNION block is executed and produces results before
            # the outer clauses are applied. If a leaf is not constrained by the
            # input set the query can time out or run out of memory. So we inline
            # VALUES (via a marker substituted at render time) and the input
            # rdf:type clause into every leaf, and the BIND into the leaves that
            # use ?http.
            #
            # The generated query has this shape:
            #
            # SELECT DISTINCT ?_1 WHERE {
            #   ?_1 rdf:type osm:way .
            #   {
            #     {
            #       VALUES ?_1·f0·input { osmnode:3843108154 }
            #       ?_1·f0·input rdf:type osm:node .
            #       ?_1·f0·m osmway:member_id ?_1·f0·input .
            #       ?_1 osmway:member ?_1·f0·m .
            #     } UNION {
            #       VALUES ?_1·f0·input { osmnode:3843108154 }
            #       BIND(IRI(REPLACE(STR(?_1·f0·input), "^https://", "http://"))
            #            AS ?_1·f0·http)
            #       ?_1·f0·http rdf:type osm:node .
            #       ?_1·f0·mwh osmway:member_id ?_1·f0·http .
            #       ?_1 osmway:member ?_1·f0·mwh .
            #     }
            #   } UNION {
            #     { ... rel: member_id ?input ... }
            #     UNION
            #     { ... BIND ?http ... rel: member_id ?http ... }
            #   }
            # }
            http_var = _variable_name(
                output_set, filter_index=filter_index, intermediate="http"
            )
            way_blank_http = _variable_name(
                output_set, filter_index=filter_index, intermediate="mwh"
            )
            rel_blank = _variable_name(
                output_set, filter_index=filter_index, intermediate="mr"
            )
            rel_blank_http = _variable_name(
                output_set, filter_index=filter_index, intermediate="mrh"
            )
            pattern.prefixes.update({"osm", "rdf", "osmway", "osmrel"})
            # The input VALUES must live inside each UNION leaf (QLever does not
            # push an outer VALUES through UNION). Use the marker mechanism so a
            # single injection fills every leaf — both render_query and the
            # composer substitute every occurrence in the matched clause, and
            # all four leaves share the same where_clause string here.
            input_values_marker = f"VALUES {input_var} {{ }}"
            pattern.injections[-1].marker = input_values_marker
            input_type = f"{input_var} rdf:type osm:node ."
            http_bind = (
                f'BIND(IRI(REPLACE(STR({input_var}), "^https://", "http://"))'
                f" AS {http_var})"
            )
            http_type = f"{http_var} rdf:type osm:node ."

            def _leaf(*lines: str) -> str:
                return "{ " + " ".join(lines) + " }"

            way_leaf = _leaf(
                input_values_marker,
                input_type,
                f"{blank_var} osmway:member_id {input_var} .",
                f"{result_variable} osmway:member {blank_var} .",
            )
            way_http_leaf = _leaf(
                input_values_marker,
                http_bind,
                http_type,
                f"{way_blank_http} osmway:member_id {http_var} .",
                f"{result_variable} osmway:member {way_blank_http} .",
            )
            rel_leaf = _leaf(
                input_values_marker,
                input_type,
                f"{rel_blank} osmrel:member_id {input_var} .",
                f"{result_variable} osmrel:member {rel_blank} .",
            )
            rel_http_leaf = _leaf(
                input_values_marker,
                http_bind,
                http_type,
                f"{rel_blank_http} osmrel:member_id {http_var} .",
                f"{result_variable} osmrel:member {rel_blank_http} .",
            )
            pattern.where_clauses.append(
                f"{{ {way_leaf} UNION {way_http_leaf} }}"
                f" UNION {{ {rel_leaf} UNION {rel_http_leaf} }}"
            )

        case RecurseFilterType.BW:
            # way → parent relations (upward)
            pattern.prefixes.add("osmrel")
            pattern.where_clauses.append(f"{blank_var} osmrel:member_id {input_var} .")
            pattern.where_clauses.append(
                f"{result_variable} osmrel:member {blank_var} ."
            )

        case RecurseFilterType.BR:
            # relation → parent relations (upward)
            pattern.prefixes.add("osmrel")
            pattern.where_clauses.append(f"{blank_var} osmrel:member_id {input_var} .")
            pattern.where_clauses.append(
                f"{result_variable} osmrel:member {blank_var} ."
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
    # Deferred import: evaluators.py imports translator.py (SetInjection), so
    # importing evaluators at module level would create a circular dependency.
    # TODO: Consider refactoring to avoid circular imports
    from qloverleaf.evaluators import translate_evaluator

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
    raise UnimplementedFeatureError(
        "UnionStatement translation is not yet implemented",
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


def _translate_out(stmt: OutStatement) -> list[SparqlPattern]:
    # OutStatement doesn't produce a set, only outputs an existing one
    pattern = SparqlPattern(output_set=None, output=True)

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
        if stmt.bb:
            # ids + bb: emit element URIs plus the element's own WKT so the
            # formatter can derive bounds (ways/relations) or lat/lon (nodes).
            # Use a site-injection marker so the input bindings land before the
            # OPTIONAL; otherwise QLever evaluates `OPTIONAL { ?x geo:hasGeometry
            # ... }` against the unbound ?x and full-scans the dataset.
            pattern.prefixes.add("geo")
            bb_marker = f"VALUES {result_variable} {{ }}"
            pattern.select_clause = f"{result_variable} ?bb_wkt"
            pattern.where_clauses.append(bb_marker)
            pattern.where_clauses.append(
                f"OPTIONAL {{ {result_variable} geo:hasGeometry ?bb_geom ."
                " ?bb_geom geo:asWKT ?bb_wkt . }"
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
    elif stmt.verbosity in (OutVerbosity.SKEL, OutVerbosity.BODY, OutVerbosity.META):
        # Skeleton: nodes get geometry, ways/relations get ordered member lists.
        # Body adds a fourth UNION branch for tags; each row is either a skel row
        # or a tag row — never both — and the formatter combines them per element.
        # Meta adds flat osmeta: triples after the UNION block, joining on the
        # element variable so every row carries the full metadata for that element.
        # All three use one branch per element type with an injection marker so
        # cold clauses land inside the branch (Option 2) and hot sets get
        # type-filtered VALUES inside the branch (Option 1).
        include_tags = stmt.verbosity in (OutVerbosity.BODY, OutVerbosity.META)
        include_meta = stmt.verbosity == OutVerbosity.META
        # bb reuses the per-member-WKT collection path: bounds is derived from
        # the union of member coordinates in the formatter. For nodes the
        # element's own ?wkt POINT from the NODE branch is already sufficient,
        # so bb adds nothing there.
        include_member_wkt = stmt.geom or stmt.bb
        pattern.prefixes |= {"rdf", "osm", "osmway", "osmrel", "geo"}
        if include_tags:
            pattern.prefixes.add("osmkey")
        if include_meta:
            pattern.prefixes.add("osmeta")
        select_parts = [result_variable]
        branches: list[str] = []
        has_members = False

        for elem_type in _OSM_TYPE_ORDER:
            if elem_type not in required_types:
                continue
            marker = _injection_marker(result_variable, elem_type)

            if elem_type == ElementType.NODE:
                branch_lines = [
                    f"{result_variable} rdf:type osm:node .",
                    marker,
                    f"{result_variable} geo:hasGeometry ?geom .",
                    "?geom geo:asWKT ?wkt .",
                ]
                if "?wkt" not in select_parts:
                    select_parts.append("?wkt")
            elif elem_type == ElementType.WAY:
                branch_lines = [
                    f"{result_variable} rdf:type osm:way .",
                    marker,
                    f"{result_variable} osmway:member ?m .",
                    "?m osmway:member_id ?member .",
                    "?m osmway:member_pos ?pos .",
                ]
                if include_member_wkt:
                    # Per-member node WKT (POINT). OPTIONAL guards against
                    # missing geometry, though in practice every node should
                    # have one. Must come after `?m osmway:member_id ?member`
                    # so ?member is bound — otherwise QLever full-scans
                    # geo:hasGeometry.
                    branch_lines.append(
                        "OPTIONAL { ?member geo:hasGeometry ?member_geom ."
                        " ?member_geom geo:asWKT ?member_wkt . }"
                    )
                for v in ["?member", "?pos"]:
                    if v not in select_parts:
                        select_parts.append(v)
                has_members = True
            else:  # RELATION
                branch_lines = [
                    f"{result_variable} rdf:type osm:relation .",
                    marker,
                    f"{result_variable} osmrel:member ?m .",
                    "?m osmrel:member_id ?member .",
                    "?m osmrel:member_pos ?pos .",
                    "?m osmrel:member_role ?role .",
                ]
                if include_member_wkt:
                    # Per-member WKT: POINT for node members, LINESTRING/POLYGON
                    # for way members, unbound for sub-relation members. Must
                    # come after `?m osmrel:member_id ?member` so ?member is
                    # bound — otherwise QLever full-scans geo:hasGeometry.
                    branch_lines.append(
                        "OPTIONAL { ?member geo:hasGeometry ?member_geom ."
                        " ?member_geom geo:asWKT ?member_wkt . }"
                    )
                for v in ["?member", "?pos", "?role"]:
                    if v not in select_parts:
                        select_parts.append(v)
                has_members = True

            branches.append("{\n  " + "\n  ".join(branch_lines) + "\n}")
            pattern.injections.append(
                SetInjection(
                    sparql_var=result_variable,
                    set_name=input_set.identifier,
                    required_types=frozenset({elem_type}),
                    marker=marker,
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

        if include_member_wkt and has_members:
            select_parts.append("?member_wkt")

        if include_meta:
            for v in ["?version", "?timestamp", "?changeset", "?uid", "?user"]:
                select_parts.append(v)

        pattern.select_clause = " ".join(select_parts)
        pattern.where_clauses.append("\nUNION\n".join(branches))

        if include_meta:
            pattern.where_clauses.extend(
                [
                    f"{result_variable} osmeta:version ?version .",
                    f"{result_variable} osmeta:timestamp ?timestamp .",
                    f"{result_variable} osmeta:changeset ?changeset .",
                    f"{result_variable} osmeta:uid ?uid .",
                    f"{result_variable} osmeta:user ?user .",
                ]
            )

        if not stmt.count:
            order_by = result_variable
            if has_members:
                order_by += " ?pos"
            pattern.order_by = order_by
            pattern.limit = stmt.limit

        if stmt.center:
            assert pattern.select_clause is not None
            pattern.select_clause += " ?centroid"
            pattern.prefixes |= {"geo", "geof"}
            pattern.where_clauses.append(f"{result_variable} geo:hasGeometry ?geom .")
            pattern.where_clauses.append("?geom geo:asWKT ?wkt .")
            pattern.where_clauses.append("BIND(geof:centroid(?wkt) AS ?centroid)")

        return [pattern]
    elif stmt.verbosity == OutVerbosity.TAGS:
        if stmt.bb:
            # tags + bb: two-branch UNION. Tag rows carry ?p/?v; bb rows carry
            # the element's own ?bb_wkt. Mirrors the body design of separating
            # tag rows from skel rows to avoid repeating WKT on every tag row.
            # Each branch puts its marker first so the input substitution binds
            # ?_1 before the subsequent triple patterns — otherwise QLever
            # full-scans the dataset (?p/?v unbound; geo:hasGeometry unbound).
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
                + f"\n  {result_variable} geo:hasGeometry ?bb_geom ."
                + "\n  ?bb_geom geo:asWKT ?bb_wkt .\n}"
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
    else:
        raise UnimplementedFeatureError(
            f"out {stmt.verbosity.value} not yet implemented",
            stmt.token,
        )

    if stmt.center:
        assert pattern.select_clause is not None
        pattern.select_clause += " ?centroid"
        pattern.prefixes |= {"geo", "geof"}
        pattern.where_clauses.append(f"{result_variable} geo:hasGeometry ?geom .")
        pattern.where_clauses.append("?geom geo:asWKT ?wkt .")
        pattern.where_clauses.append("BIND(geof:centroid(?wkt) AS ?centroid)")

    if not stmt.count:
        pattern.order_by = result_variable
        pattern.limit = stmt.limit

    return [pattern]


def _translate_recurse(stmt: RecurseStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "RecurseStatement translation is not yet implemented",
        stmt.token,
    )


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
