from qloverleaf.exceptions import QueryWarning
from qloverleaf.query_context import Bbox
from qloverleaf.transformer import (
    BboxFilter,
    CompleteStatement,
    DifferenceStatement,
    ElementType,
    ForeachStatement,
    ForStatement,
    IfStatement,
    Query,
    QueryStatement,
    Statement,
    UnionStatement,
)

_ANY = frozenset({ElementType.NODE, ElementType.WAY, ElementType.RELATION})


def _as_filter(bbox: Bbox) -> BboxFilter:
    return BboxFilter(
        south=bbox.south,
        west=bbox.west,
        north=bbox.north,
        east=bbox.east,
        token=None,
        output_types=_ANY,
    )


def _crosses_antimeridian(f: BboxFilter) -> bool:
    return float(f.west) > float(f.east)


def _intersect(bboxes: list[BboxFilter], warnings: list[QueryWarning]) -> BboxFilter:
    # Take the tightest bound at each edge, preserving the original string value
    # from whichever source wins. Callers must guard against antimeridian-crossing
    # bboxes (west > east) before calling this.
    south = max(bboxes, key=lambda b: float(b.south)).south
    west = max(bboxes, key=lambda b: float(b.west)).west
    north = min(bboxes, key=lambda b: float(b.north)).north
    east = min(bboxes, key=lambda b: float(b.east)).east
    token = next((b.token for b in bboxes if b.token is not None), None)
    if float(south) >= float(north):
        warnings.append(
            QueryWarning("Bounding box intersection is empty: south >= north", token)
        )
    return BboxFilter(
        south=south,
        west=west,
        north=north,
        east=east,
        token=token,
        output_types=_ANY,
    )


def _reconcile(
    stmt: QueryStatement,
    global_filter: BboxFilter | None,
    warnings: list[QueryWarning],
) -> None:
    explicit = [f for f in stmt.filters if isinstance(f, BboxFilter)]
    all_bboxes = ([global_filter] if global_filter else []) + explicit
    if len(all_bboxes) <= 1:
        # Zero bboxes, or exactly one with no global to merge: inject global if present.
        if global_filter:
            stmt.filters.insert(0, global_filter)
        return
    if any(_crosses_antimeridian(b) for b in all_bboxes):
        # Intersection is not well-defined when a bbox crosses the antimeridian;
        # inject global as an extra filter and leave explicit bboxes unchanged.
        if global_filter:
            stmt.filters.insert(0, global_filter)
        return
    merged = _intersect(all_bboxes, warnings)
    stmt.filters = [merged] + [f for f in stmt.filters if not isinstance(f, BboxFilter)]


def _walk(
    stmts: list[Statement],
    global_filter: BboxFilter | None,
    warnings: list[QueryWarning],
) -> None:
    for stmt in stmts:
        if isinstance(stmt, QueryStatement):
            _reconcile(stmt, global_filter, warnings)
        elif isinstance(stmt, (ForeachStatement, ForStatement, CompleteStatement)):
            _walk(stmt.body, global_filter, warnings)
        elif isinstance(stmt, UnionStatement):
            _walk(stmt.members, global_filter, warnings)
        elif isinstance(stmt, DifferenceStatement):
            _walk([stmt.left_statement, stmt.right_statement], global_filter, warnings)
        elif isinstance(stmt, IfStatement):
            _walk(stmt.then_body, global_filter, warnings)
            _walk(stmt.else_body or [], global_filter, warnings)


def optimize(ir: Query, global_bbox: Bbox | None) -> None:
    """Reconcile BboxFilters in-place: merge per-statement BboxFilters with the
    global bbox into a single filter per QueryStatement."""
    global_filter = _as_filter(global_bbox) if global_bbox else None
    _walk(ir.statements, global_filter, ir.warnings)
