from dataclasses import dataclass, field

from qloverleaf.exceptions import UnimplementedFeatureError, UnsupportedFeatureError
from qloverleaf.transform import (
    CompleteStatement,
    ElementType,
    ForeachStatement,
    ForStatement,
    IfStatement,
    IsInStatement,
    ItemStatement,
    MapToAreaStatement,
    OutStatement,
    QueryFilter,
    QueryStatement,
    RecurseStatement,
    Statement,
    UnionStatement,
)


@dataclass
class ValuesInjection:
    sparql_var: str  # e.g. "?a0"
    set_name: str  # versioned set name to look up in set state, e.g. "a0"


@dataclass
class SparqlPattern:
    result_variable: str  # e.g. "?a0"
    distinct: bool = False
    prefixes: set[str] = field(default_factory=set)
    where_clauses: list[str] = field(default_factory=list)
    injections: list[ValuesInjection] = field(default_factory=list)


def _variable_name(
    set_name: str,
    set_version: int,
    filter_index: int | None = None,
    intermediate: str | None = None,
) -> str:
    base = f"?{set_name}{set_version}"
    if filter_index is not None:
        base += f"·{filter_index}"
    if intermediate is not None:
        base += f"·{intermediate}"
    return base


_OSM_TYPE_NAMES: dict[ElementType, str] = {
    ElementType.NODE: "node",
    ElementType.WAY: "way",
    ElementType.RELATION: "relation",
}
# Canonical ordering for multi-type UNION clauses.
_OSM_TYPE_ORDER = [ElementType.NODE, ElementType.WAY, ElementType.RELATION]


def translate(statement: Statement) -> SparqlPattern:
    if isinstance(statement, QueryStatement):
        return _translate_query(statement)
    if isinstance(statement, UnionStatement):
        return _translate_union(statement)
    if isinstance(statement, ItemStatement):
        return _translate_item(statement)
    if isinstance(statement, RecurseStatement):
        return _translate_recurse(statement)
    if isinstance(statement, MapToAreaStatement):
        return _translate_map_to_area(statement)
    if isinstance(statement, IsInStatement):
        return _translate_is_in(statement)
    if isinstance(statement, OutStatement):
        return _translate_out(statement)
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


def _translate_query(statement: QueryStatement) -> SparqlPattern:
    result_variable = _variable_name(
        statement.output_set.name, statement.output_set.version
    )
    pattern = SparqlPattern(result_variable=result_variable)
    _add_type_filter(statement.element_types, result_variable, pattern)
    for f in statement.filters:
        _add_query_filter(f, result_variable, pattern)
    return pattern


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
    result_variable: str,
    pattern: SparqlPattern,
) -> None:
    raise UnimplementedFeatureError(
        "query filter translation is not yet implemented", f.token
    )


def _dump_sparql_pattern(pattern: SparqlPattern) -> str:
    lines = [
        f"result_variable: {pattern.result_variable}",
        f"distinct: {pattern.distinct}",
        f"prefixes: {sorted(pattern.prefixes)}",
        "where_clauses:",
    ]
    for clause in pattern.where_clauses:
        lines.append(f"  {clause}")
    lines.append("injections:")
    for inj in pattern.injections:
        lines.append(f"  {inj.sparql_var} <- {inj.set_name}")
    return "\n".join(lines)


def _translate_union(stmt: UnionStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "UnionStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_item(stmt: ItemStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "ItemStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_recurse(stmt: RecurseStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "RecurseStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_map_to_area(stmt: MapToAreaStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "MapToAreaStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_is_in(stmt: IsInStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "IsInStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_out(stmt: OutStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "OutStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_foreach(stmt: ForeachStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "ForeachStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_for(stmt: ForStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "ForStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_complete(stmt: CompleteStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "CompleteStatement translation is not yet implemented",
        stmt.token,
    )


def _translate_if(stmt: IfStatement) -> SparqlPattern:
    raise UnimplementedFeatureError(
        "IfStatement translation is not yet implemented",
        stmt.token,
    )
