import dataclasses
import re
from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import Enum
from typing import Any

from lark import Token, Transformer, Tree
from lark.exceptions import VisitError

from qloverleaf.exceptions import (
    QueryError,
    UnimplementedFeatureError,
    UnsupportedFeatureError,
)


@dataclass
class Warning:
    message: str
    token: Token | None


# Basic Types


class ElementType(Enum):
    NODE = "node"
    WAY = "way"
    RELATION = "relation"
    AREA = "area"
    DERIVED = "derived"  # derived elements are not supported in the POC


class TagFilterOp(Enum):
    EQ = "="
    NEQ = "!="
    REGEX = "~"
    NOT_REGEX = "!~"


class RecurseFilterType(Enum):
    BN = "bn"
    BW = "bw"
    BR = "br"
    W = "w"
    R = "r"


class BinaryOperator(Enum):
    OR = "||"
    AND = "&&"


class UnaryOperator(Enum):
    NOT = "!"
    NEGATE = "-"


class CompareOperator(Enum):
    EQUAL = "=="
    NOT_EQUAL = "!="
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    GREATER_THAN = ">"


class AddOperator(Enum):
    ADD = "+"
    SUBTRACT = "-"


class MultiplyOperator(Enum):
    MULTIPLY = "*"
    DIVIDE = "/"


class MetadataAttribute(Enum):
    ID = "id"
    TYPE = "type"
    VERSION = "version"
    TIMESTAMP = "timestamp"
    CHANGESET = "changeset"
    UID = "uid"
    USER = "user"


class CoordinateAxis(Enum):
    LAT = "lat"
    LON = "lon"


class ConversionFunction(Enum):
    NUMBER = "number"
    DATE = "date"


class TypeCheckFunction(Enum):
    IS_NUMBER = "is_number"
    IS_DATE = "is_date"


class CountType(Enum):
    NODES = "nodes"
    WAYS = "ways"
    RELATIONS = "relations"
    NW = "nw"
    WR = "wr"
    NR = "nr"
    NWR = "nwr"
    DERIVEDS = "deriveds"

    # OUT_VERB
    # RECURSE_DIR
    # TIMELINE_TYPE


class OutVerbosity(Enum):
    IDS = "ids"
    SKEL = "skel"
    TAGS = "tags"
    BODY = "body"
    META = "meta"


class OutSortOrder(Enum):
    ASC = "asc"
    QT = "qt"


class RecurseDir(Enum):
    DOWN_RELATIONS = ">>"
    UP_RELATIONS = "<<"
    DOWN = ">"
    UP = "<"


@dataclass
class IntRange:
    min_count: int
    max_count: int | None
    exact: bool
    token: Token


@dataclass
class LatLon:
    lat: str
    lon: str
    token: Token


# Set Reference


@dataclass
class SetReference:
    name: str  # canonical name; "_" if implicit
    token: Token | None  # None if implicit
    version: int = 0  # filled in by Phase 2
    # None = set types are indefinite
    required_types: frozenset[ElementType] | None = field(default=None)
    content_types: frozenset[ElementType] | None = field(default=None)

    @property
    def identifier(self) -> str:
        """Returns the versioned set name used as a key in set_state (e.g., 'a1')."""
        return f"{self.name}{self.version}"


# Set Assignment


@dataclass
class SetAssignment:
    set_reference: SetReference


_NODE = frozenset({ElementType.NODE})
_WAY = frozenset({ElementType.WAY})
_RELATION = frozenset({ElementType.RELATION})
_AREA = frozenset({ElementType.AREA})
_NWR = frozenset({ElementType.NODE, ElementType.WAY, ElementType.RELATION})
_NWRA = frozenset(
    {ElementType.NODE, ElementType.WAY, ElementType.RELATION, ElementType.AREA}
)
_WR = frozenset({ElementType.WAY, ElementType.RELATION})
_NW = frozenset({ElementType.NODE, ElementType.WAY})
_NR = frozenset({ElementType.NODE, ElementType.RELATION})
_NONE: frozenset[ElementType] = frozenset()

_ELEMENT_TYPE_MAP: dict[str, frozenset[ElementType]] = {
    "element_type_node": _NODE,
    "element_type_way": _WAY,
    "element_type_relation": _RELATION,
    "element_type_nwr": _NWR,
    "element_type_nw": _NW,
    "element_type_wr": _WR,
    "element_type_nr": _NR,
    "element_type_area": _AREA,
    "element_type_derived": frozenset({ElementType.DERIVED}),
}

# Scalar Types


class ScalarType(Enum):
    BOOLEAN = "xsd:boolean"
    DATETIME = "xsd:dateTime"
    DECIMAL = "xsd:decimal"
    DOUBLE = "xsd:double"
    INT = "xsd:int"
    LITERAL = "plain_literal"
    NULL = "null"  # no scalar input
    # None = indeterminate type


_NON_EBV_TYPES = frozenset({ScalarType.DATETIME})
_NUMERIC_TYPES = frozenset({ScalarType.INT, ScalarType.DECIMAL, ScalarType.DOUBLE})

_NUMERIC_RANK = {ScalarType.INT: 0, ScalarType.DECIMAL: 1, ScalarType.DOUBLE: 3}


def _promote_numeric_type(a: ScalarType, b: ScalarType) -> ScalarType:
    assert a in _NUMERIC_TYPES
    assert b in _NUMERIC_TYPES
    return a if _NUMERIC_RANK[a] >= _NUMERIC_RANK[b] else b


# Evaluator Classes


@dataclass(kw_only=True)
class Evaluator:
    token: Token
    output_type: ScalarType | None = None


@dataclass
class TernaryEvaluator(Evaluator):
    condition: Evaluator
    true_expression: Evaluator
    false_expression: Evaluator


@dataclass
class BinaryEvaluator(Evaluator):
    operator: BinaryOperator
    operands: list[Evaluator]


@dataclass
class UnaryEvaluator(Evaluator):
    operator: UnaryOperator
    operand: Evaluator


@dataclass
class CompareEvaluator(Evaluator):
    left_operand: Evaluator
    operator: CompareOperator
    right_operand: Evaluator


@dataclass
class AddEvaluator(Evaluator):
    left_operand: Evaluator
    operator: AddOperator
    right_operand: Evaluator


@dataclass
class MultiplyEvaluator(Evaluator):
    left_operand: Evaluator
    operator: MultiplyOperator
    right_operand: Evaluator


# ...


@dataclass
class LiteralEvaluator(Evaluator):
    value: str


@dataclass
class MetadataEvaluator(Evaluator):
    attribute: MetadataAttribute
    target_set: SetReference | None = None


@dataclass
class TagValueEvaluator(Evaluator):
    evaluator: LiteralEvaluator
    target_set: SetReference | None = None


@dataclass
class IsTagEvaluator(Evaluator):
    key: str
    target_set: SetReference | None = None


@dataclass
class CoordinateEvaluator(Evaluator):
    axis: CoordinateAxis
    target_set: SetReference | None = None


@dataclass
class ConversionEvaluator(Evaluator):
    function: ConversionFunction
    operand: Evaluator


@dataclass
class SuffixEvaluator(Evaluator):
    operand: Evaluator


@dataclass
class AbsEvaluator(Evaluator):
    operand: Evaluator


@dataclass
class TypeCheckEvaluator(Evaluator):
    function: TypeCheckFunction
    operand: Evaluator


@dataclass
class IsClosedEvaluator(Evaluator):
    target_set: SetReference | None = None


@dataclass
class LengthEvaluator(Evaluator):
    target_set: SetReference | None = None


@dataclass
class CountEvaluator(Evaluator):
    count_type: CountType
    input_set: SetReference


@dataclass
class ValEvaluator(Evaluator):
    set_reference: SetReference


# Query Filter Classes


@dataclass(kw_only=True)
class QueryFilter:
    token: Token | None  # None when set_reference is implicit
    output_types: frozenset[ElementType] | None = field(default=None)


@dataclass
class TagKeyFilter(QueryFilter):
    key: str
    absent: bool


@dataclass
class TagValueFilter(QueryFilter):
    key: str
    op: TagFilterOp
    value: str
    case_insensitive: bool


@dataclass
class BboxFilter(QueryFilter):
    south: str
    west: str
    north: str
    east: str


@dataclass
class IdFilter(QueryFilter):
    ids: list[int]


@dataclass
class AroundSetFilter(QueryFilter):
    radius: str
    set_reference: SetReference


@dataclass
class AroundPointFilter(QueryFilter):
    radius: str
    lat: str
    lon: str


@dataclass
class AroundLineFilter(QueryFilter):
    radius: str
    points: list[LatLon]


@dataclass
class PolygonFilter(QueryFilter):
    points: list[LatLon]


@dataclass
class NewerFilter(QueryFilter):
    timestamp: datetime


@dataclass
class UserFilter(QueryFilter):
    users: list[str]


@dataclass
class UidFilter(QueryFilter):
    uids: list[int]


@dataclass
class AreaSetFilter(QueryFilter):
    set_reference: SetReference


@dataclass
class AreaIdFilter(QueryFilter):
    area_id: int


@dataclass
class RecurseFilter(QueryFilter):
    recurse_type: RecurseFilterType
    set_reference: SetReference
    role: str | None


@dataclass
class WayCountFilter(QueryFilter):
    set_reference: SetReference
    min_count: int
    max_count: int | None  # None means open upper bound (N-)
    exact: bool  # True if no dash (exact match)


@dataclass
class SetFilter(QueryFilter):
    set_reference: SetReference


@dataclass
class PivotFilter(QueryFilter):
    set_reference: SetReference


@dataclass
class IfFilter(QueryFilter):
    evaluator: Evaluator


# Top Level Classes


@dataclass(kw_only=True)
class Statement:
    token: Token | None

    def get_output_types(
        self,
        warnings: list[Warning],
    ) -> frozenset[ElementType] | None:
        return None


@dataclass
class Query:
    statements: list[Statement]
    warnings: list[Warning]


# Simple Statement Classes


@dataclass
class QueryStatement(Statement):
    element_types: frozenset[ElementType]
    filters: list[QueryFilter]
    output_set: SetReference

    def get_output_types(
        self,
        warnings: list[Warning],
    ) -> frozenset[ElementType] | None:
        current_types: frozenset[ElementType] | None = self.element_types
        for filter in self.filters:
            filter_output = filter.output_types
            if isinstance(filter, SetFilter):
                # SetFilter intersects the stream with the named set's types.
                # Use Phase 2 content_types if available; otherwise indefinite.
                filter_output = filter.set_reference.content_types
            if filter_output is None:
                current_types = None
                break
            assert current_types is not None
            current_types = current_types & filter_output
            filter.output_types = current_types
            if current_types == _NONE:
                warnings.append(
                    Warning(
                        f"Filter cannot output any elements given "
                        f"{[e.name for e in current_types]} as input",
                        filter.token,
                    )
                )
                break
        return current_types


# Block Statement Classes


@dataclass
class ForeachStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    body: list[Statement]

    def get_output_types(
        self, warnings: list[Warning]
    ) -> frozenset[ElementType] | None:
        return self.input_set.content_types


@dataclass
class ForStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    evaluator: Evaluator
    body: list[Statement]

    def get_output_types(
        self, warnings: list[Warning]
    ) -> frozenset[ElementType] | None:
        return self.input_set.content_types


@dataclass
class CompleteStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    max_iterations: int | None
    body: list[Statement]

    def get_output_types(
        self, warnings: list[Warning]
    ) -> frozenset[ElementType] | None:
        # union_inward fires once per iteration, after all body statements finish,
        # examining only the final value of the input set. Walk forward tracking
        # the current type of the input set: each write replaces the previous value.
        accum_name = self.input_set.name

        def walk(
            statements: list[Statement],
            current: frozenset[ElementType],
        ) -> frozenset[ElementType] | None:
            for statement in statements:
                if isinstance(statement, (ForeachStatement, ForStatement)):
                    if statement.output_set.name == accum_name:
                        # loop exit overwrites the output set with empty
                        current = _NONE
                    else:
                        # walk body; writes to accum_name persist after the loop
                        body_result = walk(statement.body, current)
                        if body_result is None:
                            return None
                        current = body_result

                # either branch may be the final writer; take the union of both outcomes
                if isinstance(statement, IfStatement):
                    then_result = walk(statement.then_body, current)
                    if then_result is None:
                        return None
                    else_result = (
                        walk(statement.else_body, current)
                        if statement.else_body
                        else current
                    )
                    if else_result is None:
                        return None
                    current = then_result | else_result

                # nested complete propagates its output set to the caller
                elif isinstance(statement, CompleteStatement):
                    if statement.output_set.name == accum_name:
                        types = statement.get_output_types(warnings)
                        if types is None:
                            return None
                        current = types

                # union -> input set: output goes directly to the input set
                elif isinstance(statement, UnionStatement):
                    if statement.output_set.name == accum_name:
                        types = statement.get_output_types(warnings)
                        if types is None:
                            return None
                        current = types
                    else:
                        # union -> other set: propagates inner ._ as a side effect;
                        # walk members to determine the final value of the input set
                        union_result = walk(
                            [m.statement for m in statement.members], current
                        )
                        if union_result is None:
                            return None
                        current = union_result

                else:
                    output_set: SetReference | None = getattr(
                        statement, "output_set", None
                    )
                    if output_set is not None and output_set.name == accum_name:
                        types = statement.get_output_types(warnings)
                        if types is None:
                            return None
                        current = types

            return current

        if self.input_set.content_types is None:
            return None
        body_final = walk(self.body, self.input_set.content_types)
        if body_final is None:
            return None
        # Single-pass approximation: models one iteration of the loop. A more
        # precise approach would repeat walk() feeding the result back as the new
        # incoming type until body_final stabilizes (fixed-point iteration).
        return self.input_set.content_types | body_final


@dataclass
class IfStatement(Statement):
    condition: Evaluator
    then_body: list[Statement]
    else_body: list[Statement] | None

    def get_output_types(
        self, warnings: list[Warning]
    ) -> frozenset[ElementType] | None:
        return _NONE


# Other Statement Classes


@dataclass
class UnionMember:
    difference: bool
    statement: Statement


@dataclass
class UnionStatement(Statement):
    members: list[UnionMember]
    output_set: SetReference

    def get_output_types(
        self,
        warnings: list[Warning],
    ) -> frozenset[ElementType] | None:
        result = _NONE
        for member in self.members:
            if isinstance(
                member.statement,
                (OutStatement, ForeachStatement, ForStatement, IfStatement),
            ):
                continue
            member_output_types = member.statement.get_output_types(warnings)
            if member.difference:
                continue
            if member_output_types is None:
                return None
            result = result | member_output_types
        if result == _NONE:
            warnings.append(
                Warning(
                    "Union statement returns no data",
                    None,
                )
            )
        return result


@dataclass
class ItemStatement(Statement):
    input_set: SetReference
    output_set: SetReference

    def get_output_types(
        self, warnings: list[Warning]
    ) -> frozenset[ElementType] | None:
        return self.input_set.content_types


@dataclass
class OutStatement(Statement):
    input_set: SetReference
    count: bool
    verbosity: OutVerbosity
    geom: bool
    bb: bool
    center: bool
    sort_order: OutSortOrder
    limit: int | None


@dataclass
class RecurseStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    recurse_dir: RecurseDir

    def get_output_types(
        self, warnings: list[Warning]
    ) -> frozenset[ElementType] | None:
        input_types = self.input_set.content_types
        if input_types is None:
            return None
        result: frozenset[ElementType] = _NONE
        if self.recurse_dir == RecurseDir.DOWN:
            if ElementType.WAY in input_types:
                result |= _NODE
            if ElementType.RELATION in input_types:
                result |= _NW
        elif self.recurse_dir == RecurseDir.DOWN_RELATIONS:
            if ElementType.WAY in input_types:
                result |= _NODE
            if ElementType.RELATION in input_types:
                result |= _NWR
        elif self.recurse_dir == RecurseDir.UP:
            if ElementType.NODE in input_types:
                result |= _WR
            if ElementType.WAY in input_types or ElementType.RELATION in input_types:
                result |= _RELATION
        elif self.recurse_dir == RecurseDir.UP_RELATIONS:
            if ElementType.NODE in input_types:
                result |= _WR
            if ElementType.WAY in input_types or ElementType.RELATION in input_types:
                result |= _RELATION
        return result


@dataclass
class IsInStatement(Statement):
    input_set: SetReference
    lat: str | None
    lon: str | None
    output_set: SetReference

    def get_output_types(
        self, warnings: list[Warning]
    ) -> frozenset[ElementType] | None:
        return _AREA


@dataclass
class MapToAreaStatement(Statement):
    input_set: SetReference
    output_set: SetReference

    def get_output_types(
        self, warnings: list[Warning]
    ) -> frozenset[ElementType] | None:
        return _AREA


# Helper Functions


def _parse_datetime(token: Token) -> datetime:
    v = str(token)
    if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
        v = v[1:-1]
    return datetime.fromisoformat(v)


_ESCAPE_MAP = {"n": "\n", "t": "\t", '"': '"', "'": "'", "\\": "\\"}


def _unquote(token: Token) -> str:
    v = str(token)
    if len(v) < 2 or v[0] not in ('"', "'") or v[-1] != v[0]:
        return v
    inner = v[1:-1]

    def replace_escape(m: re.Match) -> str:  # type: ignore[type-arg]
        seq = m.group(1)
        if seq[0] == "u":
            return chr(int(seq[1:], 16))
        return _ESCAPE_MAP[seq]

    return re.sub(r'\\(u[0-9A-Fa-f]{4}|[nt"\'\\])', replace_escape, inner)


# Phase 2 — Set Version Assignment


_SetState = tuple[int, frozenset[ElementType] | None]
_State = dict[str, _SetState]


def _stamp_read(ref: SetReference, state: _State, warnings: list[Warning]) -> None:
    if ref.name not in state:
        warnings.append(
            Warning(f"Uninitialized set .{ref.name} contains no data", ref.token)
        )
        state[ref.name] = (0, _NONE)
    version, content_types = state[ref.name]
    ref.version = version
    ref.content_types = content_types
    assert content_types is not None
    if ref.required_types is not None and content_types & ref.required_types == _NONE:
        have = [e.name for e in content_types] if content_types else ["nothing"]
        need = [e.name for e in ref.required_types]
        warnings.append(
            Warning(
                f"Set .{ref.name} contains {have} but requires {need}",
                ref.token,
            )
        )


def _stamp_write(
    ref: SetReference,
    state: _State,
    types: frozenset[ElementType] | None,
) -> None:
    version = (state[ref.name][0] if ref.name in state else 0) + 1
    state[ref.name] = (version, types)
    ref.version = version
    ref.content_types = types
    if types is not None and types & _NWR and types & _AREA:
        raise UnimplementedFeatureError(
            f"Set cannot contain both {types & _NWR} and {types & _AREA}", ref.token
        )


def _stamp_evaluator(
    evaluator: Evaluator, state: _State, warnings: list[Warning]
) -> None:
    for f in fields(evaluator):
        val = getattr(evaluator, f.name)
        if isinstance(val, SetReference):
            _stamp_read(val, state, warnings)
        elif isinstance(val, Evaluator):
            _stamp_evaluator(val, state, warnings)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, Evaluator):
                    _stamp_evaluator(item, state, warnings)


def _stamp_filter_refs(
    filter_: QueryFilter, state: _State, warnings: list[Warning]
) -> None:
    set_reference: SetReference | None = getattr(filter_, "set_reference", None)
    if set_reference is not None:
        _stamp_read(set_reference, state, warnings)
    elif isinstance(filter_, IfFilter):
        _stamp_evaluator(filter_.evaluator, state, warnings)


def _walk_stmts(stmts: list[Statement], state: _State, warnings: list[Warning]) -> None:
    for stmt in stmts:
        _walk_stmt(stmt, state, warnings)


def _walk_stmt(stmt: Statement, state: _State, warnings: list[Warning]) -> None:
    if isinstance(stmt, IfStatement):
        _walk_if(stmt, state, warnings)
    elif isinstance(stmt, (ForeachStatement, ForStatement)):
        _walk_loop(stmt, state, warnings)
    elif isinstance(stmt, CompleteStatement):
        _walk_complete(stmt, state, warnings)
    elif isinstance(stmt, UnionStatement):
        _walk_union(stmt, state, warnings)
    else:
        input_set: SetReference | None = getattr(stmt, "input_set", None)
        if input_set is not None:
            _stamp_read(input_set, state, warnings)
        if isinstance(stmt, QueryStatement):
            for f in stmt.filters:
                _stamp_filter_refs(f, state, warnings)
        output_set: SetReference | None = getattr(stmt, "output_set", None)
        if output_set is not None:
            _stamp_write(output_set, state, stmt.get_output_types(warnings))


def _walk_loop(
    stmt: ForeachStatement | ForStatement,
    state: _State,
    warnings: list[Warning],
) -> None:
    _stamp_read(stmt.input_set, state, warnings)
    if isinstance(stmt, ForStatement):
        _stamp_evaluator(stmt.evaluator, state, warnings)
    _stamp_write(stmt.output_set, state, stmt.get_output_types(warnings))
    _walk_stmts(stmt.body, state, warnings)
    _stamp_write(stmt.output_set, state, _NONE)


def _walk_complete(
    stmt: CompleteStatement,
    state: _State,
    warnings: list[Warning],
) -> None:
    _stamp_read(stmt.input_set, state, warnings)
    _stamp_write(stmt.output_set, state, stmt.input_set.content_types)
    _walk_stmts(stmt.body, state, warnings)
    _stamp_write(stmt.output_set, state, stmt.get_output_types(warnings))


def _walk_union(stmt: UnionStatement, state: _State, warnings: list[Warning]) -> None:
    for member in stmt.members:
        _walk_stmt(member.statement, state, warnings)
    _stamp_write(stmt.output_set, state, stmt.get_output_types(warnings))


def _walk_if(stmt: IfStatement, state: _State, warnings: list[Warning]) -> None:
    _stamp_evaluator(stmt.condition, state, warnings)
    then_state = dict(state)
    else_state = dict(state)
    _walk_stmts(stmt.then_body, then_state, warnings)
    _walk_stmts(stmt.else_body or [], else_state, warnings)

    def _written(branch: _State) -> set[str]:
        return {n for n in branch if branch[n][0] > state.get(n, (0, _NONE))[0]}

    written = _written(then_state) | _written(else_state)
    for name in written:
        then_types = then_state.get(name, state.get(name, (0, _NONE)))[1]
        else_types = else_state.get(name, state.get(name, (0, _NONE)))[1]
        if then_types is None or else_types is None:
            merged_types: frozenset[ElementType] | None = None
        else:
            merged_types = then_types | else_types
        state[name] = (state.get(name, (0, _NONE))[0] + 1, merged_types)


def _resolve_types(query: Query) -> None:
    state: _State = {}
    _walk_stmts(query.statements, state, query.warnings)


# Overpass Transformer


class OverpassTransformer(Transformer[Token, Query]):
    def __init__(self) -> None:
        super().__init__()
        self.warnings: list[Warning] = []

    def transform(self, tree: Tree[Token]) -> Query:
        try:
            return super().transform(tree)
        except VisitError as e:
            raise e.orig_exc from e

    # Query Transform
    def query(self, children: list[Any]) -> Query:
        statements: list[Statement] = []
        for child in children:
            if isinstance(child, Statement):
                statements.append(child)
        result = Query(statements=statements, warnings=self.warnings)
        _resolve_types(result)
        return result

    # Global Settings Transform

    def global_setting(self, children: list[Any]) -> None:
        return None

    # Basic Type Transforms

    def tag_key(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

    def tag_key_regex(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

    def tag_value(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

    def tag_value_regex(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

    def regex_case_insensitive(self, children: list[Any]) -> bool:
        return True

    def around_radius(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

    def around_lat_lon(self, children: list[Any]) -> LatLon:
        lat_tok, lon_tok = children
        assert isinstance(lat_tok, Token)
        assert isinstance(lon_tok, Token)
        return LatLon(lat=lat_tok.value, lon=lon_tok.value, token=lat_tok)

    def poly_lat_lon(self, children: list[Any]) -> LatLon:
        lat_tok, lon_tok = children
        assert isinstance(lat_tok, Token)
        assert isinstance(lon_tok, Token)
        return LatLon(lat=lat_tok.value, lon=lon_tok.value, token=lat_tok)

    def set_ref(self, children: list[Any]) -> SetReference:
        assert isinstance(children[0], Token)
        return SetReference(
            name=str(children[0]),
            token=children[0],
        )

    def recurse_role(self, children: list[Any]) -> str:
        assert isinstance(children[0], Token)
        return _unquote(children[0])

    def int_range(self, children: list[Any]) -> IntRange:
        assert isinstance(children[0], Token)
        if len(children) == 1:
            return IntRange(int(children[0]), int(children[0]), True, children[0])
        elif len(children) == 2:
            return IntRange(int(children[0]), None, False, children[0])
        else:
            assert isinstance(children[2], Token)
            return IntRange(int(children[0]), int(children[2]), False, children[0])

    def set_name(self, children: list[Any]) -> SetReference:
        assert isinstance(children[0], Token)
        return SetReference(
            name=str(children[0]),
            token=children[0],
        )

    # Query Filter Transforms

    def tag_filter_exists(self, children: list[Any]) -> TagKeyFilter:
        return TagKeyFilter(
            key=_unquote(children[0]),
            absent=False,
            token=children[0],
            output_types=_NWRA,
        )

    def tag_filter_absent(self, children: list[Any]) -> TagKeyFilter:
        return TagKeyFilter(
            key=_unquote(children[0]),
            absent=True,
            token=children[0],
            output_types=_NWRA,
        )

    def tag_filter_eq(self, children: list[Any]) -> TagValueFilter:
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.EQ,
            value=_unquote(children[1]),
            case_insensitive=False,
            token=children[0],
            output_types=_NWRA,
        )

    def tag_filter_neq(self, children: list[Any]) -> TagValueFilter:
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.NEQ,
            value=_unquote(children[1]),
            case_insensitive=False,
            token=children[0],
            output_types=_NWRA,
        )

    def tag_filter_regex(self, children: list[Any]) -> TagValueFilter:
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.REGEX,
            value=_unquote(children[1]),
            case_insensitive=case_insensitive,
            token=children[0],
            output_types=_NWRA,
        )

    def tag_filter_not_regex(self, children: list[Any]) -> TagValueFilter:
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.NOT_REGEX,
            value=_unquote(children[1]),
            case_insensitive=case_insensitive,
            token=children[0],
            output_types=_NWRA,
        )

    def tag_filter_key_regex(self, children: list[Any]) -> None:
        # best known translation forces a full scan over all triples and times out
        raise UnsupportedFeatureError(
            "Key regex filter [~key~value] is not supported", children[0]
        )

    def bbox_filter(self, children: list[Any]) -> BboxFilter:
        s_tok, w_tok, n_tok, e_tok = children
        assert isinstance(s_tok, Token)
        assert isinstance(w_tok, Token)
        assert isinstance(n_tok, Token)
        assert isinstance(e_tok, Token)
        south, west, north, east = (
            s_tok.value,
            w_tok.value,
            n_tok.value,
            e_tok.value,
        )
        if float(south) >= float(north):
            self.warnings.append(
                Warning(
                    "Bounding box south >= north: filter will always be empty",
                    s_tok,
                )
            )
        return BboxFilter(
            south=south,
            west=west,
            north=north,
            east=east,
            token=s_tok,
            output_types=_NWRA,
        )

    def id_filter_single(self, children: list[Any]) -> IdFilter:
        assert isinstance(children[0], Token)
        return IdFilter(
            ids=[int(children[0])],
            token=children[0],
            output_types=_NWRA,
        )

    def id_filter_list(self, children: list[Any]) -> IdFilter:
        assert isinstance(children[0], Token)
        return IdFilter(
            ids=[int(t) for t in children],
            token=children[0],
            output_types=_NWRA,
        )

    def around_set_filter(self, children: list[Any]) -> AroundSetFilter:
        if len(children) == 1:
            set_reference = SetReference(
                name="_",
                token=None,
                required_types=_NWR,
            )
            radius_token = children[0]
        else:
            set_reference, radius_token = children[0], children[1]
            set_reference.required_types = _NWR
        assert isinstance(radius_token, Token)
        return AroundSetFilter(
            radius=radius_token.value,
            set_reference=set_reference,
            token=radius_token,
            output_types=_NWRA,
        )

    def around_point_filter(self, children: list[Any]) -> AroundPointFilter:
        radius_token = children[0]
        lat_lon = children[1]
        assert isinstance(radius_token, Token)
        assert isinstance(lat_lon, LatLon)
        return AroundPointFilter(
            radius=radius_token.value,
            lat=lat_lon.lat,
            lon=lat_lon.lon,
            token=radius_token,
            output_types=_NWRA,
        )

    def around_line_filter(self, children: list[Any]) -> AroundLineFilter:
        radius_token = children[0]
        assert isinstance(radius_token, Token)
        return AroundLineFilter(
            radius=radius_token.value,
            points=list(children[1:]),
            token=radius_token,
            output_types=_NWRA,
        )

    def polygon_filter(self, children: list[Any]) -> PolygonFilter:
        assert isinstance(children[0], LatLon)
        return PolygonFilter(
            points=list(children),
            token=children[0].token,
            output_types=_NWRA,
        )

    def newer_filter(self, children: list[Any]) -> NewerFilter:
        assert isinstance(children[0], Token)
        return NewerFilter(
            timestamp=_parse_datetime(children[0]),
            token=children[0],
            output_types=_NWR,
        )

    def changed_filter(self, children: list[Any]) -> None:
        # QLever does not have attic data
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("changed filter is not supported", children[0])

    def user_filter(self, children: list[Any]) -> UserFilter:
        assert isinstance(children[0], Token)
        return UserFilter(
            users=[_unquote(t) for t in children],
            token=children[0],
            output_types=_NWR,
        )

    def uid_filter(self, children: list[Any]) -> UidFilter:
        assert isinstance(children[0], Token)
        return UidFilter(
            uids=[int(t) for t in children],
            token=children[0],
            output_types=_NWR,
        )

    def user_touched_filter(self, children: list[Any]) -> None:
        # QLever does not have attic data
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError(
            "user_touched filter is not supported", children[0]
        )

    def uid_touched_filter(self, children: list[Any]) -> None:
        # QLever does not have attic data
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError(
            "uid_touched filter is not supported", children[0]
        )

    def area_set_filter(self, children: list[Any]) -> AreaSetFilter:
        if children:
            ref = children[0]
            assert isinstance(ref, SetReference)
            ref.required_types = _AREA
            return AreaSetFilter(set_reference=ref, token=ref.token, output_types=_NWRA)
        return AreaSetFilter(
            set_reference=SetReference(name="_", token=None, required_types=_AREA),
            token=None,
            output_types=_NWRA,
        )

    def area_id_filter(self, children: list[Any]) -> AreaIdFilter:
        assert isinstance(children[0], Token)
        return AreaIdFilter(
            area_id=int(children[0]),
            token=children[0],
            output_types=_NWRA,
        )

    def recurse_filter(self, children: list[Any]) -> RecurseFilter:
        type_token = children[0]
        assert isinstance(type_token, Token)
        recurse_type = RecurseFilterType(str(type_token))
        set_reference = SetReference(name="_", token=None)
        role: str | None = None
        for child in children[1:]:
            if isinstance(child, SetReference):
                set_reference = child
            elif isinstance(child, str):
                role = child
        match recurse_type:
            case RecurseFilterType.BN:
                set_reference.required_types = _NODE
                output_types: frozenset[ElementType] | None = _WR
            case RecurseFilterType.BW:
                set_reference.required_types = _WAY
                output_types = _RELATION
            case RecurseFilterType.BR:
                set_reference.required_types = _RELATION
                output_types = _RELATION
            case RecurseFilterType.W:
                set_reference.required_types = _WAY
                output_types = _NODE
            case RecurseFilterType.R:
                set_reference.required_types = _RELATION
                output_types = _NWR
        return RecurseFilter(
            recurse_type=recurse_type,
            set_reference=set_reference,
            role=role,
            token=type_token,
            output_types=output_types,
        )

    def way_count_filter(self, children: list[Any]) -> WayCountFilter:
        if isinstance(children[0], SetReference):
            set_reference = children[0]
            set_reference.required_types = _WAY
            int_range = children[1]
        else:
            set_reference = SetReference(name="_", token=None, required_types=_WAY)
            int_range = children[0]
        assert isinstance(int_range, IntRange)
        return WayCountFilter(
            set_reference=set_reference,
            min_count=int_range.min_count,
            max_count=int_range.max_count,
            exact=int_range.exact,
            token=int_range.token,
            output_types=_NODE,
        )

    def way_link_filter(self, children: list[Any]) -> None:
        # no known translation to Sparql (see way-count-filters.md)
        raise UnsupportedFeatureError(
            "way_link filter is not supported", children[0].token
        )

    def set_filter(self, children: list[Any]) -> SetFilter:
        assert isinstance(children[0], Token)
        return SetFilter(
            set_reference=SetReference(name=str(children[0]), token=children[0]),
            token=children[0],
        )

    def pivot_filter(self, children: list[Any]) -> PivotFilter:
        if children:
            set_reference = children[0]
            assert isinstance(set_reference, SetReference)
            set_reference.required_types = _AREA
            return PivotFilter(
                set_reference=set_reference,
                token=set_reference.token,
                output_types=_WR,
            )
        return PivotFilter(
            set_reference=SetReference(name="_", token=None, required_types=_AREA),
            output_types=_WR,
            token=None,
        )

    def if_filter(self, children: list[Any]) -> IfFilter:
        evaluator = children[0]
        assert isinstance(evaluator, Evaluator)
        return IfFilter(
            evaluator=evaluator,
            token=evaluator.token,
            output_types=_NWRA,
        )

    def set_assignment(self, children: list[Any]) -> SetAssignment:
        assert isinstance(children[0], SetReference)
        return SetAssignment(set_reference=children[0])

    # Statement Transform

    def statement(self, children: list[Any]) -> Statement:
        assert len(children) == 1
        assert isinstance(children[0], Statement)
        return children[0]

    # Simple Statement Transforms

    def query_stmt(self, children: list[Any]) -> QueryStatement:
        element_type_tree = children[0]
        assert isinstance(element_type_tree, Tree)
        element_types = _ELEMENT_TYPE_MAP[str(element_type_tree.data)]
        token = element_type_tree.children[0]
        assert isinstance(token, Token)
        filters: list[QueryFilter] = []
        output_set = SetReference(name="_", token=None)
        for child in children[1:]:
            if isinstance(child, QueryFilter):
                filters.append(child)
            elif isinstance(child, SetAssignment):
                output_set = child.set_reference
        return QueryStatement(
            element_types=element_types,
            filters=filters,
            output_set=output_set,
            token=token,
        )

    # Block Statement Transforms

    def block_body(self, children: list[Any]) -> list[Any]:
        return list(children)

    def foreach_stmt(self, children: list[Any]) -> ForeachStatement:
        input_set = SetReference(name="_", token=None)
        output_set = SetReference(name="_", token=None)
        body: list[Any] = []
        for child in children:
            if isinstance(child, SetReference):
                input_set = child
            elif isinstance(child, SetAssignment):
                output_set = child.set_reference
            elif isinstance(child, list):
                body = child
        input_set.required_types = _NWRA
        return ForeachStatement(
            input_set=input_set,
            output_set=output_set,
            body=body,
            token=input_set.token,
        )

    def for_stmt(self, children: list[Any]) -> ForStatement:
        input_set = SetReference(name="_", token=None)
        output_set = SetReference(name="_", token=None)
        evaluator = None
        body: list[Any] = []
        for child in children:
            if isinstance(child, SetReference):
                input_set = child
            elif isinstance(child, SetAssignment):
                output_set = child.set_reference
            elif isinstance(child, Evaluator):
                evaluator = child
            elif isinstance(child, list):
                body = child
        assert evaluator is not None
        input_set.required_types = _NWRA
        return ForStatement(
            input_set=input_set,
            output_set=output_set,
            evaluator=evaluator,
            body=body,
            token=evaluator.token,
        )

    def complete_stmt(self, children: list[Any]) -> CompleteStatement:
        input_set = SetReference(name="_", token=None)
        output_set = SetReference(name="_", token=None)
        max_iterations = None
        body: list[Any] = []
        for child in children:
            if isinstance(child, SetReference):
                input_set = child
            elif isinstance(child, SetAssignment):
                output_set = child.set_reference
            elif isinstance(child, Token) and child.type == "INTEGER":
                max_iterations = int(child)
            else:
                body.append(child)
        input_set.required_types = _NWRA
        return CompleteStatement(
            input_set=input_set,
            output_set=output_set,
            max_iterations=max_iterations,
            body=body,
            token=input_set.token,
        )

    def if_stmt(self, children: list[Any]) -> IfStatement:
        condition = children[0]
        assert isinstance(condition, Evaluator)
        then_body = children[1]
        else_body = children[2] if len(children) > 2 else None
        return IfStatement(
            condition=condition,
            then_body=then_body,
            else_body=else_body,
            token=condition.token,
        )

    def retro_stmt(self, children: list[Any]) -> None:
        # QLever does not have attic data
        evaluator = children[0]
        assert isinstance(evaluator, Evaluator)
        raise UnsupportedFeatureError(
            "retro statement is not supported", evaluator.token
        )

    # Other Statement Transforms

    def union_member(self, children: list[Any]) -> UnionMember:
        if isinstance(children[0], Token):
            assert children[0].type == "NEGATE_OP"
            return UnionMember(difference=True, statement=children[1])
        return UnionMember(difference=False, statement=children[0])

    def union_body(self, children: list[Any]) -> list[UnionMember]:
        return list(children)

    def union_stmt(self, children: list[Any]) -> UnionStatement:
        # All statement types are permitted as union members. out and if are allowed
        # because syntax and semantics permit them, unlike the legacy implementation.
        # foreach and for are allowed, consistent with the legacy implementation; body
        # assignments do not contribute to the union but modified sets may. complete is
        # allowed, consistent with the legacy implementation, but we will not reproduce
        # the input set bug. All other statements are allowed.
        members: list[UnionMember] = children[0]
        output_set = SetReference(name="_", token=None)
        if len(children) == 2:
            assert isinstance(children[1], SetAssignment)
            output_set = children[1].set_reference
        if members:
            token = members[0].statement.token
        else:
            token = output_set.token
        return UnionStatement(
            members=members,
            output_set=output_set,
            token=token,
        )

    def item_stmt(self, children: list[Any]) -> ItemStatement:
        input_set = children[0]
        assert isinstance(input_set, SetReference)
        input_set.required_types = _NWRA
        output_set = SetReference(name="_", token=None)
        if len(children) == 2:
            assert isinstance(children[1], SetAssignment)
            output_set = children[1].set_reference
        return ItemStatement(
            input_set=input_set,
            output_set=output_set,
            token=input_set.token,
        )

    def out_token(self, children: list[Any]) -> Any:
        return children[0]

    def out_stmt(self, children: list[Any]) -> OutStatement:
        input_set = SetReference(name="_", token=None)
        token: Token | None = None
        seen_verbs: dict[str, Token] = {}
        verbosity_token: Token | None = None
        count_token: Token | None = None
        geom_token: Token | None = None
        bb_token: Token | None = None
        center_token: Token | None = None
        sort_token: Token | None = None
        limit_token: Token | None = None

        for child in children:
            if isinstance(child, SetReference):
                input_set = child
                if token is None:
                    token = child.token
            elif isinstance(child, BboxFilter):
                raise UnsupportedFeatureError(
                    # Overpass support for this feature is idiosyncratic
                    "bbox_filter in out statement is not supported",
                    child.token,
                )
            elif isinstance(child, Token):
                if child.type == "OUT_VERB":
                    verb = str(child)
                    if verb in seen_verbs:
                        raise QueryError(f"duplicate out token: {verb!r}", child)
                    seen_verbs[verb] = child
                    if token is None:
                        token = child
                    if verb == "noids":
                        # Overpass support for this feature is broken
                        raise UnsupportedFeatureError("noids is not supported", child)
                    elif verb in ("ids", "skel", "tags", "body", "meta"):
                        if verbosity_token is not None:
                            raise QueryError(
                                f"out verbosity conflict: "
                                f"{str(verbosity_token)!r} and {verb!r}",
                                child,
                            )
                        verbosity_token = child
                    elif verb == "count":
                        count_token = child
                    elif verb == "geom":
                        geom_token = child
                    elif verb == "bb":
                        bb_token = child
                    elif verb == "center":
                        center_token = child
                    elif verb in ("asc", "qt"):
                        if sort_token is not None:
                            raise QueryError(
                                f"out sort order conflict: "
                                f"{str(sort_token)!r} and {verb!r}",
                                child,
                            )
                        sort_token = child
                elif child.type == "INTEGER":
                    if limit_token is not None:
                        raise QueryError("duplicate INTEGER in out statement", child)
                    limit_token = child
                    if token is None:
                        token = child

        if geom_token is not None and bb_token is not None:
            raise QueryError("out geom and bb are mutually exclusive", geom_token)

        if count_token is not None:
            for conflicting, name in (
                (verbosity_token, str(verbosity_token) if verbosity_token else None),
                (geom_token, "geom"),
                (bb_token, "bb"),
                (center_token, "center"),
                (sort_token, str(sort_token) if sort_token else None),
                (limit_token, "INTEGER"),
            ):
                if conflicting is not None:
                    raise QueryError(
                        f"out count cannot be combined with {name!r}", count_token
                    )

        input_set.required_types = _NWRA

        return OutStatement(
            input_set=input_set,
            count=count_token is not None,
            verbosity=(
                OutVerbosity(str(verbosity_token))
                if verbosity_token is not None
                else OutVerbosity.BODY
            ),
            geom=geom_token is not None,
            bb=bb_token is not None,
            center=center_token is not None,
            sort_order=(
                OutSortOrder(str(sort_token))
                if sort_token is not None
                else OutSortOrder.ASC
            ),
            limit=int(limit_token) if limit_token is not None else None,
            token=token,
        )

    def recurse_stmt(self, children: list[Any]) -> RecurseStatement:
        input_set = SetReference(name="_", token=None)
        output_set = SetReference(name="_", token=None)
        recurse_dir = None
        token = None
        for child in children:
            if isinstance(child, SetReference):
                input_set = child
                token = child.token if token is None else token
            elif isinstance(child, SetAssignment):
                output_set = child.set_reference
            elif isinstance(child, Token) and child.type == "RECURSE_DIR":
                recurse_dir = RecurseDir(child.value)
                token = child if token is None else token
        assert recurse_dir is not None
        match recurse_dir:
            case RecurseDir.DOWN:
                input_set.required_types = _NWR
            case RecurseDir.DOWN_RELATIONS:
                input_set.required_types = _NWR
            case RecurseDir.UP | RecurseDir.UP_RELATIONS:
                input_set.required_types = _NWR
        return RecurseStatement(
            input_set=input_set,
            output_set=output_set,
            recurse_dir=recurse_dir,
            token=token,
        )

    def is_in_stmt(self, children: list[Any]) -> IsInStatement:
        input_set = SetReference(name="_", token=None)
        output_set = SetReference(name="_", token=None)
        lat: str | None = None
        lon: str | None = None
        token = None
        for child in children:
            if isinstance(child, SetReference):
                input_set = child
                token = child.token if token is None else token
            elif isinstance(child, Token) and child.type == "NUMBER":
                if lat is None:
                    lat = child.value
                    token = child if token is None else token
                else:
                    lon = child.value
            elif isinstance(child, SetAssignment):
                output_set = child.set_reference
                token = child.set_reference.token if token is None else token
        input_set.required_types = _NODE
        return IsInStatement(
            input_set=input_set,
            lat=lat,
            lon=lon,
            output_set=output_set,
            token=token,
        )

    def timeline_stmt(self, children: list[Any]) -> None:
        # QLever does not have attic data
        raise UnsupportedFeatureError(
            "timeline statement is not supported", children[0]
        )

    def local_stmt(self, children: list[Any]) -> None:
        # The local statement exposes the interal data format within Overpass
        # TODO: Consider adding an output format type for raw QLever JSON
        raise UnsupportedFeatureError(
            "local statement is not supported", children[0] if children else None
        )

    def convert_stmt(self, children: list[Any]) -> None:
        # Sparql has no notion of synthetic data types but this could be supported
        # with a purely local implementation
        raise UnimplementedFeatureError(
            "convert statement is not implemented", children[0]
        )

    def make_stmt(self, children: list[Any]) -> None:
        # Sparql has no notion of synthetic data types but this could be supported
        # with a purely local implementation
        raise UnimplementedFeatureError(
            "make statement is not implemented", children[0]
        )

    def map_to_area_stmt(self, children: list[Any]) -> MapToAreaStatement:
        input_set = SetReference(name="_", token=None, required_types=_WR)
        output_set = SetReference(name="_", token=None, required_types=_AREA)
        token = None
        for child in children:
            if isinstance(child, SetReference):
                input_set = child
                input_set.required_types = _WR
                token = child.token if token is None else token
            elif isinstance(child, SetAssignment):
                output_set = child.set_reference
                token = child.set_reference.token if token is None else token
        return MapToAreaStatement(
            input_set=input_set,
            output_set=output_set,
            token=token,
        )

    def compare_stmt(self, children: list[Any]) -> None:
        # QLever does not have attic data
        raise UnsupportedFeatureError(
            "compare statement is not supported",
            children[0] if children else None,
        )

    # Evaluator Transforms

    def ternary_expr(self, children: list[Any]) -> TernaryEvaluator:
        condition = children[0]
        assert isinstance(condition, Evaluator)
        if condition.output_type in _NON_EBV_TYPES:
            self.warnings.append(
                Warning(
                    f"Condition with {condition.output_type.value} will always be true",
                    children[0].token,
                )
            )

        true_expression = children[1]
        assert isinstance(true_expression, Evaluator)
        then_type = true_expression.output_type

        false_expression = children[2]
        assert isinstance(false_expression, Evaluator)
        else_type = false_expression.output_type

        if then_type is None:
            output_type = None
            self.warnings.append(
                Warning(
                    "Then branch type is indeterminate and may cause SPARQL errors",
                    children[1].token,
                )
            )
        elif else_type is None:
            output_type = None
            self.warnings.append(
                Warning(
                    "Else branch type is indeterminate and may cause SPARQL errors",
                    children[2].token,
                )
            )
        elif then_type == else_type:
            output_type = then_type
        elif then_type in _NUMERIC_TYPES and else_type in _NUMERIC_TYPES:
            output_type = _promote_numeric_type(then_type, else_type)
        else:
            output_type = None
            self.warnings.append(
                Warning(
                    "Incompatible types in ternary branches may cause SPARQL errors: "
                    f"( {then_type.value} / {else_type.value} )",
                    children[1].token,
                )
            )

        return TernaryEvaluator(
            condition=condition,
            output_type=output_type,
            true_expression=true_expression,
            false_expression=false_expression,
            token=children[0].token,
        )

    def or_expr(self, children: list[Any]) -> BinaryEvaluator:
        for child in children:
            assert isinstance(child, Evaluator)
            if child.output_type in _NON_EBV_TYPES:
                self.warnings.append(
                    Warning(
                        f"Operand using {child.output_type.value} will always be true",
                        child.token,
                    )
                )
        return BinaryEvaluator(
            operator=BinaryOperator.OR,
            operands=children,
            output_type=ScalarType.BOOLEAN,
            token=children[0].token,
        )

    def and_expr(self, children: list[Any]) -> BinaryEvaluator:
        for child in children:
            assert isinstance(child, Evaluator)
            if child.output_type in _NON_EBV_TYPES:
                self.warnings.append(
                    Warning(
                        f"Operand using {child.output_type.value} will always be true",
                        child.token,
                    )
                )
        return BinaryEvaluator(
            operator=BinaryOperator.AND,
            operands=children,
            output_type=ScalarType.BOOLEAN,
            token=children[0].token,
        )

    def not_expr(self, children: list[Any]) -> UnaryEvaluator:
        operand = children[1]
        assert isinstance(operand, Evaluator)
        if operand.output_type in _NON_EBV_TYPES:
            self.warnings.append(
                Warning(
                    f"Expression with {operand.output_type.value} will always be false",
                    operand.token,
                )
            )
        return UnaryEvaluator(
            operator=UnaryOperator.NOT,
            operand=operand,
            output_type=ScalarType.BOOLEAN,
            token=children[0],
        )

    def compare_expr(self, children: list[Any]) -> CompareEvaluator:
        left_operand = children[0]
        assert isinstance(left_operand, Evaluator)
        left_type = left_operand.output_type

        right_operand = children[2]
        assert isinstance(right_operand, Evaluator)
        right_type = right_operand.output_type

        if left_type is None:
            self.warnings.append(
                Warning(
                    "Operand type is indeterminate and may cause SPARQL errors",
                    left_operand.token,
                )
            )
        elif right_type is None:
            self.warnings.append(
                Warning(
                    "Operand type is indeterminate and may cause SPARQL errors",
                    right_operand.token,
                )
            )
        elif left_type != right_type and not (
            left_type in _NUMERIC_TYPES and right_type in _NUMERIC_TYPES
        ):
            self.warnings.append(
                Warning(
                    f"Incompatible operand types {left_type.value} and "
                    f"{right_type.value} may cause SPARQL errors",
                    left_operand.token,
                )
            )

        return CompareEvaluator(
            left_operand=children[0],
            operator=CompareOperator(children[1].value),
            right_operand=children[2],
            output_type=ScalarType.BOOLEAN,
            token=children[0].token,
        )

    def add_expr(self, children: list[Any]) -> AddEvaluator:
        operator = AddOperator(children[1].value)

        left_operand = children[0]
        assert isinstance(left_operand, Evaluator)
        left_type = left_operand.output_type

        right_operand = children[2]
        assert isinstance(right_operand, Evaluator)
        right_type = right_operand.output_type

        if left_type is None or right_type is None:
            output_type = None
            token = left_operand.token if left_type is None else right_operand.token
            self.warnings.append(
                Warning(
                    "Operand type is indeterminate and may cause SPARQL errors", token
                )
            )
        elif left_type in _NUMERIC_TYPES and right_type in _NUMERIC_TYPES:
            # numeric addition/subtraction
            output_type = _promote_numeric_type(left_type, right_type)
        elif (
            operator == AddOperator.ADD
            and left_type == ScalarType.LITERAL
            and right_type == ScalarType.LITERAL
        ):
            # string concatenation
            output_type = ScalarType.LITERAL
        else:
            output_type = None
            op_name = (
                "addition/concatenation"
                if operator == AddOperator.ADD
                else "subtraction"
            )
            self.warnings.append(
                Warning(
                    f"Operand types are incompatible with {op_name}: "
                    f"( {left_type.value} / {right_type.value} )",
                    left_operand.token,
                )
            )

        return AddEvaluator(
            left_operand=left_operand,
            operator=operator,
            right_operand=right_operand,
            output_type=output_type,
            token=children[0].token,
        )

    def mul_expr(self, children: list[Any]) -> MultiplyEvaluator:
        operator = MultiplyOperator(children[1].value)

        left_operand = children[0]
        assert isinstance(left_operand, Evaluator)
        left_type = left_operand.output_type

        right_operand = children[2]
        assert isinstance(right_operand, Evaluator)
        right_type = right_operand.output_type

        if left_type is None or right_type is None:
            output_type = None
            token = left_operand.token if left_type is None else right_operand.token
            self.warnings.append(
                Warning(
                    "Operand type is indeterminate and may cause SPARQL errors", token
                )
            )
        elif left_type in _NUMERIC_TYPES and right_type in _NUMERIC_TYPES:
            output_type = _promote_numeric_type(left_type, right_type)
        else:
            output_type = None
            op_name = (
                "multiplication"
                if operator == MultiplyOperator.MULTIPLY
                else "division"
            )
            self.warnings.append(
                Warning(
                    f"Operand types are incompatible with {op_name}: "
                    f"( {left_type.value} / {right_type.value} )",
                    left_operand.token,
                )
            )

        return MultiplyEvaluator(
            left_operand=left_operand,
            operator=operator,
            right_operand=right_operand,
            output_type=output_type,
            token=children[0].token,
        )

    def unary_expr(self, children: list[Any]) -> UnaryEvaluator:
        return UnaryEvaluator(
            operator=UnaryOperator.NEGATE,
            operand=children[1],
            token=children[0],
        )

    def literal_expr(self, children: list[Any]) -> LiteralEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return LiteralEvaluator(value=_unquote(token), token=token)

    def id_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(attribute=MetadataAttribute(token.value), token=token)

    def type_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(attribute=MetadataAttribute(token.value), token=token)

    def tag_value_expr(self, children: list[Any]) -> TagValueEvaluator:
        token = children[0].token
        assert isinstance(token, Token)
        evaluator = children[0]
        if not isinstance(evaluator, LiteralEvaluator):
            # the best known translation forces a complete scan over all triples and
            # times out (see tag-filters.md)
            raise UnsupportedFeatureError(
                "t[...] with a dynamic key expression is not supported", token
            )
        return TagValueEvaluator(evaluator=evaluator, token=token)

    def is_tag_expr(self, children: list[Any]) -> IsTagEvaluator:
        token = children[0]
        key = _unquote(children[0])
        assert isinstance(token, Token)
        return IsTagEvaluator(key=key, token=token)

    def keys_expr(self, children: list[Any]) -> None:
        # Returns all tag key names as semicolon-separated string; no SPARQL equivalent
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("keys() evaluator is not supported", children[0])

    def generic_tag_expr(self, children: list[Any]) -> None:
        # implemented only in the context of convert/make which are unsupported
        raise UnsupportedFeatureError(
            "the generic tag evaluator is not supported", children[0]
        )

    def version_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(attribute=MetadataAttribute(token.value), token=token)

    def timestamp_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(attribute=MetadataAttribute(token.value), token=token)

    def changeset_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(attribute=MetadataAttribute(token.value), token=token)

    def uid_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(attribute=MetadataAttribute(token.value), token=token)

    def user_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(attribute=MetadataAttribute(token.value), token=token)

    def count_tags_expr(self, children: list[Any]) -> None:
        # TODO: implement count_tags_expr transform
        assert isinstance(children[0], Token)
        raise UnimplementedFeatureError("count_tags() is not implemented", children[0])

    def count_members_expr(self, children: list[Any]) -> None:
        # TODO: implement count_members_expr transform
        assert isinstance(children[0], Token)
        raise UnimplementedFeatureError(
            "count_members() is not implemented", children[0]
        )

    def count_distinct_members_expr(self, children: list[Any]) -> None:
        # TODO: implement count_distinct_members_expr transform
        assert isinstance(children[0], Token)
        raise UnimplementedFeatureError(
            "count_distinct_members() is not implemented", children[0]
        )

    def count_by_role_expr(self, children: list[Any]) -> None:
        # TODO: implement count_by_role_expr transform
        raise UnimplementedFeatureError(
            "count_by_role() is not implemented", children[0].token
        )

    def count_distinct_by_role_expr(self, children: list[Any]) -> None:
        # TODO: implement count_distinct_by_role_expr transform
        raise UnimplementedFeatureError(
            "count_distinct_by_role() is not implemented", children[0].token
        )

    def is_closed_expr(self, children: list[Any]) -> IsClosedEvaluator:
        assert isinstance(children[0], Token)
        return IsClosedEvaluator(token=children[0])

    def lat_expr(self, children: list[Any]) -> CoordinateEvaluator:
        assert isinstance(children[0], Token)
        return CoordinateEvaluator(axis=CoordinateAxis.LAT, token=children[0])

    def lon_expr(self, children: list[Any]) -> CoordinateEvaluator:
        assert isinstance(children[0], Token)
        return CoordinateEvaluator(axis=CoordinateAxis.LON, token=children[0])

    def geom_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("geom() is not supported", children[0])

    def length_expr(self, children: list[Any]) -> LengthEvaluator:
        assert isinstance(children[0], Token)
        return LengthEvaluator(token=children[0])

    def center_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        raise UnsupportedFeatureError("center() is not supported", children[0].token)

    def trace_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        raise UnsupportedFeatureError("trace() is not supported", children[0].token)

    def hull_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        raise UnsupportedFeatureError("hull() is not supported", children[0].token)

    def pt_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        raise UnsupportedFeatureError("pt() is not supported", children[0].token)

    def lstr_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        raise UnsupportedFeatureError("lstr() is not supported", children[0].token)

    def poly_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        raise UnsupportedFeatureError("poly() is not supported", children[0].token)

    def per_member_expr(self, children: list[Any]) -> None:
        # Returns a semicolon-separated list; requires lrs operators to process, which
        # are unsupported
        raise UnsupportedFeatureError(
            "per_member() is not supported", children[0].token
        )

    def per_vertex_expr(self, children: list[Any]) -> None:
        # individual vertices are not addressable in Sparql
        raise UnsupportedFeatureError(
            "per_vertex() is not supported", children[0].token
        )

    def pos_expr(self, children: list[Any]) -> None:
        # valid only in the context of per_member()/per_vertex() which are unsupported
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("pos() is not supported", children[0])

    def mtype_expr(self, children: list[Any]) -> None:
        # valid only in the context of per_member()/per_vertex() which are unsupported
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("mtype() is not supported", children[0])

    def ref_expr(self, children: list[Any]) -> None:
        # valid only in the context of per_member()/per_vertex() which are unsupported
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("ref() is not supported", children[0])

    def role_expr(self, children: list[Any]) -> None:
        # valid only in the context of per_member()/per_vertex() which are unsupported
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("role() is not supported", children[0])

    def angle_expr(self, children: list[Any]) -> None:
        # valid only in the context of per_member()/per_vertex() which are unsupported
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("angle() is not supported", children[0])

    def number_expr(self, children: list[Any]) -> ConversionEvaluator:
        return ConversionEvaluator(
            function=ConversionFunction.NUMBER,
            operand=children[0],
            token=children[0].token,
        )

    def date_expr(self, children: list[Any]) -> ConversionEvaluator:
        return ConversionEvaluator(
            function=ConversionFunction.DATE,
            operand=children[0],
            token=children[0].token,
        )

    def suffix_expr(self, children: list[Any]) -> SuffixEvaluator:
        return SuffixEvaluator(operand=children[0], token=children[0].token)

    def abs_expr(self, children: list[Any]) -> AbsEvaluator:
        return AbsEvaluator(operand=children[0], token=children[0].token)

    def is_number_expr(self, children: list[Any]) -> TypeCheckEvaluator:
        return TypeCheckEvaluator(
            function=TypeCheckFunction.IS_NUMBER,
            operand=children[0],
            token=children[0].token,
        )

    def is_date_expr(self, children: list[Any]) -> TypeCheckEvaluator:
        return TypeCheckEvaluator(
            function=TypeCheckFunction.IS_DATE,
            operand=children[0],
            token=children[0].token,
        )

    def unique_expr(self, children: list[Any]) -> None:
        # TODO: Revisit the decision to support the u evaluator
        # There may be a translation for this feature (see evaluator-filters.md)
        raise UnsupportedFeatureError("u() is not supported", children[0].token)

    def min_expr(self, children: list[Any]) -> None:
        # TODO: Revisit the decision to support the min evaluator
        # Does static typing resolve the ambiguity between lexical and numeric ordering?
        raise UnsupportedFeatureError("min() is not supported", children[0].token)

    def max_expr(self, children: list[Any]) -> None:
        # TODO: Revisit the decision to support the max evaluator
        # Does static typing resolve the ambiguity between lexical and numeric ordering?
        raise UnsupportedFeatureError("max() is not supported", children[0].token)

    def sum_expr(self, children: list[Any]) -> None:
        # TODO: Implement sum_expr transform
        raise UnimplementedFeatureError("sum() is not supported", children[0].token)

    def set_expr(self, children: list[Any]) -> None:
        # Returns a semicolon separated list of values; no Sparql translation
        raise UnsupportedFeatureError("set() is not supported", children[0].token)

    def gcat_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        raise UnsupportedFeatureError("gcat() is not supported", children[0].token)

    def count_expr(self, children: list[Any]) -> CountEvaluator:
        count_type_token = children[-1]
        assert isinstance(count_type_token, Token)
        if len(children) == 2:
            set_reference = children[0]
        else:
            set_reference = SetReference(name="_", token=None)
        count_type = CountType(str(count_type_token))
        if count_type == CountType.DERIVEDS:
            raise UnsupportedFeatureError(
                "count(deriveds) is not supported", count_type_token
            )
        return CountEvaluator(
            count_type=count_type,
            input_set=set_reference,
            token=count_type_token,
        )

    def lrs_in_expr(self, children: list[Any]) -> None:
        # operates on a semicolon separated list of values; no Sparql translation
        raise UnsupportedFeatureError("lrs_in() is not supported", children[0].token)

    def lrs_isect_expr(self, children: list[Any]) -> None:
        # operates on a semicolon separated list of values; no Sparql translation
        raise UnsupportedFeatureError("lrs_isect() is not supported", children[0].token)

    def lrs_union_expr(self, children: list[Any]) -> None:
        # operates on a semicolon separated list of values; no Sparql translation
        raise UnsupportedFeatureError("lrs_union() is not supported", children[0].token)

    def lrs_min_expr(self, children: list[Any]) -> None:
        # operates on a semicolon separated list of values; no Sparql translation
        raise UnsupportedFeatureError("lrs_min() is not supported", children[0].token)

    def lrs_max_expr(self, children: list[Any]) -> None:
        # operates on a semicolon separated list of values; no Sparql translation
        raise UnsupportedFeatureError("lrs_max() is not supported", children[0].token)

    def val_expr(self, children: list[Any]) -> ValEvaluator:
        # set_reference must be the output set of an enclosing for_stmt (sets are
        # global, so any for loop on the stack is valid, not just the innermost). Only
        # that set is populated with per-iteration values.
        # TODO: (deferred) validate in a semantic pass — walk the IR with a stack of
        # for loop output set names; raise if set_reference.name matches none of them.
        set_reference = children[0]
        assert isinstance(set_reference, SetReference)
        assert set_reference.token is not None
        return ValEvaluator(set_reference=set_reference, token=set_reference.token)


def _dump_ir_node(obj: Any, indent: int = 0) -> str:
    prefix = "  " * indent
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        name = type(obj).__name__
        lines = f"{prefix}{name}(\n"
        for f in dataclasses.fields(obj):
            val = getattr(obj, f.name)
            lines += f"{prefix}  {f.name}="
            if dataclasses.is_dataclass(val) and not isinstance(val, type):
                lines += "\n" + _dump_ir_node(val, indent + 2)
            elif isinstance(val, list):
                if val:
                    lines += "[\n"
                    for item in val:
                        lines += _dump_ir_node(item, indent + 2)
                    lines += f"{prefix}  ]\n"
                else:
                    lines += "[]\n"
            elif isinstance(val, frozenset):
                lines += "{" + ", ".join(e.name for e in val) + "}\n"
            elif isinstance(val, Enum):
                lines += f"{val.value!r}\n"
            else:
                lines += f"{val!r}\n"
        lines += f"{prefix})\n"
        return lines
    elif isinstance(obj, list):
        if not obj:
            return f"{prefix}[]\n"
        lines = f"{prefix}[\n"
        for item in obj:
            lines += _dump_ir_node(item, indent + 1)
        lines += f"{prefix}]\n"
        return lines
    else:
        return f"{prefix}{obj!r}\n"


def _dump_ir(ir: Query) -> str:
    lines = ""
    for warning in ir.warnings:
        lines += f"Warning: {warning.message}\n"
    for stmt in ir.statements:
        lines += _dump_ir_node(stmt)
    return lines
