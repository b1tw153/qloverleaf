from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from qloverleaf.exceptions import UnimplementedFeatureError, UnsupportedFeatureError

if TYPE_CHECKING:
    from qloverleaf.interpreter import SetState
from qloverleaf.transform import (
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
    IfStatement,
    IsInStatement,
    ItemStatement,
    MapToAreaStatement,
    NewerFilter,
    OutStatement,
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
    must_materialize: bool = (
        False  # True if this input must be materialized (cannot compose)
    )


@dataclass
class SparqlPattern:
    output_set: SetReference
    materialize: bool = False
    prefixes: set[str] = field(default_factory=set)
    select_clause: str | None = None
    distinct: bool = False
    group_by: str | None = None
    order_by: str | None = None
    where_clauses: list[str] = field(default_factory=list)
    injections: list[SetInjection] = field(default_factory=list)
    limit: int | None = None

    @property
    def result_variable(self) -> str:
        """SPARQL variable name with ? prefix (e.g., '?craters1')"""
        return f"?{self.output_set.identifier}"

    @property
    def result_set_name(self) -> str:
        """Set state key without ? prefix (e.g., 'craters1')"""
        return self.output_set.identifier


def _dump_sparql_pattern(pattern: SparqlPattern) -> str:
    lines = [
        f"output_set: .{pattern.output_set.name} (v{pattern.output_set.version})",
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
        distinct = "DISTINCT " if pattern.distinct else ""
        lines.append(f"SELECT {distinct}{pattern.result_variable} WHERE {{")

    # VALUES injections
    for injection in pattern.injections:
        entry = set_state.get(injection.set_name)
        uris = entry.nwr_results if entry and entry.nwr_results else []
        uri_list = " ".join(f"<{u}>" for _, u in uris)
        lines.append(f"  VALUES {injection.sparql_var} {{ {uri_list} }}")

    # WHERE clauses
    for clause in pattern.where_clauses:
        lines.append(f"  {clause}")

    lines.append("}")

    # GROUP BY
    if pattern.group_by:
        lines.append(f"GROUP BY {pattern.group_by}")

    # ORDER BY
    if pattern.order_by:
        lines.append(f"ORDER BY {pattern.order_by}")

    # LIMIT
    if pattern.limit:
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
        raise UnimplementedFeatureError(
            "area query translation is not yet implemented", None
        )
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
    # elif isinstance(f, IfFilter): ...
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
    uris = [f"{_OSM_TYPE_PREFIXES[t]}:{id_}" for t in osm_types for id_ in f.ids]
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
    pattern.injections.append(
        SetInjection(sparql_var=ref_var, set_name=f.set_reference.identifier)
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
    pattern.where_clauses.append(f"{area_uri} ogc:sfContains {result_variable} .")


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
    pattern.injections.append(
        SetInjection(sparql_var=area_var, set_name=f.set_reference.identifier)
    )
    pattern.where_clauses.append(f"{area_var} ogc:sfContains {result_variable} .")


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

    pattern.injections.append(
        SetInjection(sparql_var=input_var, set_name=f.set_reference.identifier)
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
            # node → parent ways/relations (upward)
            pattern.prefixes.update({"osmway", "osmrel"})
            # TODO: Need UNION for both URI schemes (http:// and https://) and both way
            # and relation parents. This is complex - will need multi-branch UNION.
            raise UnimplementedFeatureError(
                "bn (node → parent) recurse filter requires complex UNION pattern",
                f.token,
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
    pattern.injections.append(
        SetInjection(
            sparql_var=way_var,
            set_name=f.set_reference.identifier,
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
        " WHERE {{"
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
        SetInjection(sparql_var=result_variable, set_name=f.set_reference.identifier)
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
    pattern.injections.append(
        SetInjection(sparql_var=result_variable, set_name=f.set_reference.identifier)
    )


# _translate_if_filter


def _translate_union(stmt: UnionStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "UnionStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_item(stmt: ItemStatement) -> list[SparqlPattern]:
    raise UnimplementedFeatureError(
        "ItemStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_out(stmt: OutStatement) -> list[SparqlPattern]:
    output_set = stmt.input_set
    pattern = SparqlPattern(output_set=output_set, materialize=True)
    result_variable = pattern.result_variable

    # Inject input set (allow composition via must_materialize=False)
    pattern.injections.append(
        SetInjection(sparql_var=result_variable, set_name=output_set.identifier)
    )

    if stmt.count:
        # Per-type count breakdown with GROUP BY
        pattern.prefixes |= {"rdf", "osm"}
        pattern.select_clause = f"?type (COUNT(DISTINCT {result_variable}) AS ?count)"
        pattern.group_by = "?type"
        pattern.where_clauses.append(f"{result_variable} rdf:type ?type .")
    else:
        raise UnimplementedFeatureError(
            "Non-count out statements not yet implemented",
            stmt.token,
        )

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
