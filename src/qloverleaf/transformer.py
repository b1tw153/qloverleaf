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
    QueryWarning,
    UnimplementedFeatureError,
    UnsupportedFeatureError,
)

# Basic Types


class ElementType(Enum):
    NODE = "node"
    WAY = "way"
    RELATION = "relation"
    # AREA = "area"  # areas are not a separate type in Qloverleaf
    # DERIVED = "derived"  # derived elements are not supported in the POC


class QueryFilterType(Enum):
    NODE = "element_type_node"
    WAY = "element_type_way"
    RELATION = "element_type_relation"
    NWR = "element_type_nwr"
    NW = "element_type_nw"
    WR = "element_type_wr"
    NR = "element_type_nr"
    AREA = "element_type_area"
    # DERIVED = "element_type_derived"


class TagFilterOp(Enum):
    EQ = "="
    NEQ = "!="
    REGEX = "~"
    NOT_REGEX = "!~"
    KEY_REGEX = "~~"


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


class AggregateOperator(Enum):
    MIN = "min"
    MAX = "max"


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


# Filters, statements, and set references carry a constrained value (YES, NO, or None
# for indeterminate). A filter is constrained if it limits index scanning in QLever to
# an acceptable scope on its own. A statement is constrained if any of its filters are
# constrained (QueryStatement), all members are constrained # (UnionStatement), or its
# input set is constrained (all others). A set reference inherits its constrained value
# from the statement that assigned to it via _stamp_write. _walk_stmt warns after each
# statement dispatch if the statement has an output set and is not constrained.
class Constrained(Enum):
    YES = "yes"
    NO = "no"
    # None = indeterminate


# Set Reference


@dataclass
class SetReference:
    name: str  # canonical name; "_" if implicit
    token: Token | None  # None if implicit
    version: int = 0  # filled in by Phase 2
    # None = set types are indefinite
    required_types: frozenset[ElementType] | None = field(default=None)
    content_types: frozenset[ElementType] | None = field(default=None)
    constrained: Constrained | None = None

    @property
    def identifier(self) -> str:
        """Returns the versioned set name used as a key in set_state (e.g., 'a1')."""
        return f"{self.name}{self.version}"


# Set Assignment


@dataclass
class SetAssignment:
    set_reference: SetReference


_NONE: frozenset[ElementType] = frozenset()
_NODE = frozenset({ElementType.NODE})
_WAY = frozenset({ElementType.WAY})
_RELATION = frozenset({ElementType.RELATION})
_AREA = frozenset({ElementType.WAY, ElementType.RELATION})
_NW = frozenset({ElementType.NODE, ElementType.WAY})
_WR = frozenset({ElementType.WAY, ElementType.RELATION})
_NR = frozenset({ElementType.NODE, ElementType.RELATION})
_NWR = frozenset({ElementType.NODE, ElementType.WAY, ElementType.RELATION})
_ANY = frozenset(
    {
        ElementType.NODE,
        ElementType.WAY,
        ElementType.RELATION,
        # ElementType.AREA,
        # ElementType.DERIVED,
    }
)

_ELEMENT_TYPES_MAP: dict[str, frozenset[ElementType]] = {
    "element_type_node": _NODE,
    "element_type_way": _WAY,
    "element_type_relation": _RELATION,
    "element_type_nwr": _NWR,
    "element_type_nw": _NW,
    "element_type_wr": _WR,
    "element_type_nr": _NR,
    "element_type_area": _AREA,
    # "element_type_derived": frozenset({ElementType.DERIVED}),
}

# Scalar Types


class ScalarType(Enum):
    BOOLEAN = "xsd:boolean"
    DATETIME = "xsd:dateTime"
    LITERAL = "plain_literal"
    NUMERIC = "numeric"
    # None = indeterminate type


_NON_EBV_TYPES = frozenset({ScalarType.DATETIME})


_INT_LITERAL = re.compile(r"^ *[+-]?\d+ *$")
_DECIMAL_LITERAL = re.compile(r"^ *[+-]?(\d+\.\d*|\d*\.\d+) *$")
_DOUBLE_LITERAL = re.compile(r"^ *[+-]?(\d+\.?\d*|\d*\.\d+)[eE][+-]?\d+ *$")


def _infer_literal_type(value: str) -> ScalarType:
    if _INT_LITERAL.fullmatch(value):
        return ScalarType.NUMERIC
    if _DECIMAL_LITERAL.fullmatch(value):
        return ScalarType.NUMERIC
    if _DOUBLE_LITERAL.fullmatch(value):
        return ScalarType.NUMERIC
    try:
        datetime.fromisoformat(value)
        return ScalarType.DATETIME
    except ValueError:
        return ScalarType.LITERAL


# Evaluator Classes


@dataclass(kw_only=True)
class Evaluator:
    token: Token
    output_type: ScalarType | None


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
    operands: list[Evaluator]
    operators: list[AddOperator]


@dataclass
class MultiplyEvaluator(Evaluator):
    operands: list[Evaluator]
    operators: list[MultiplyOperator]


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
class CountTagsEvaluator(Evaluator):
    target_set: SetReference | None = None


@dataclass
class CountMembersEvaluator(Evaluator):
    distinct: bool = False
    target_set: SetReference | None = None


@dataclass
class CountByRoleEvaluator(Evaluator):
    role: Evaluator
    distinct: bool = False
    target_set: SetReference | None = None


@dataclass
class IsClosedEvaluator(Evaluator):
    target_set: SetReference | None = None


@dataclass
class LengthEvaluator(Evaluator):
    target_set: SetReference | None = None


@dataclass
class UniqueEvaluator(Evaluator):
    input_set: SetReference
    evaluator: Evaluator


@dataclass
class MinMaxEvaluator(Evaluator):
    input_set: SetReference
    operator: AggregateOperator
    evaluator: Evaluator


@dataclass
class SumEvaluator(Evaluator):
    input_set: SetReference
    evaluator: Evaluator


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

    @property
    def constrained(self) -> Constrained | None:
        return None


@dataclass
class TagKeyFilter(QueryFilter):
    key: str
    absent: bool

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.NO


@dataclass
class TagValueFilter(QueryFilter):
    key: str
    op: TagFilterOp
    value: str
    case_insensitive: bool

    @property
    def constrained(self) -> Constrained | None:
        if self.op == TagFilterOp.EQ:
            return Constrained.YES
        else:
            return Constrained.NO


@dataclass
class BboxFilter(QueryFilter):
    south: str
    west: str
    north: str
    east: str

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.NO


@dataclass
class IdFilter(QueryFilter):
    ids: list[int]

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.YES


@dataclass
class AroundSetFilter(QueryFilter):
    radius: str
    set_reference: SetReference

    @property
    def constrained(self) -> Constrained | None:
        if self.set_reference is None:
            return None
        return Constrained.NO


@dataclass
class AroundPointFilter(QueryFilter):
    radius: str
    lat: str
    lon: str

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.NO


@dataclass
class AroundLineFilter(QueryFilter):
    radius: str
    points: list[LatLon]

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.NO


@dataclass
class PolygonFilter(QueryFilter):
    points: list[LatLon]

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.NO


@dataclass
class NewerFilter(QueryFilter):
    timestamp: datetime

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.NO


@dataclass
class UserFilter(QueryFilter):
    users: list[str]

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.YES


@dataclass
class UidFilter(QueryFilter):
    uids: list[int]

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.YES


@dataclass
class AreaSetFilter(QueryFilter):
    set_reference: SetReference

    @property
    def constrained(self) -> Constrained | None:
        return self.set_reference.constrained


@dataclass
class AreaIdFilter(QueryFilter):
    area_id: int

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.YES


@dataclass
class RecurseFilter(QueryFilter):
    recurse_type: RecurseFilterType
    set_reference: SetReference
    role: str | None

    @property
    def constrained(self) -> Constrained | None:
        return self.set_reference.constrained


@dataclass
class WayCountFilter(QueryFilter):
    set_reference: SetReference
    min_count: int
    max_count: int | None  # None means open upper bound (N-)
    exact: bool  # True if no dash (exact match)

    @property
    def constrained(self) -> Constrained | None:
        if self.set_reference.constrained is None:
            return None
        return Constrained.NO


@dataclass
class SetFilter(QueryFilter):
    set_reference: SetReference

    @property
    def constrained(self) -> Constrained | None:
        return self.set_reference.constrained


@dataclass
class PivotFilter(QueryFilter):
    set_reference: SetReference

    @property
    def constrained(self) -> Constrained | None:
        return self.set_reference.constrained


@dataclass
class IfFilter(QueryFilter):
    evaluator: Evaluator

    @property
    def constrained(self) -> Constrained | None:
        return Constrained.NO


# Top Level Classes


@dataclass(kw_only=True)
class Statement:
    token: Token | None

    def get_output_types(
        self,
        warnings: list[QueryWarning],
    ) -> frozenset[ElementType] | None:
        return None

    @property
    def constrained(self) -> Constrained | None:
        return None


@dataclass
class Query:
    statements: list[Statement]
    warnings: list[QueryWarning]


# Simple Statement Classes


@dataclass
class QueryStatement(Statement):
    filter_type: QueryFilterType
    element_types: frozenset[ElementType]
    filters: list[QueryFilter]
    output_set: SetReference

    def get_output_types(
        self,
        warnings: list[QueryWarning],
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
                    QueryWarning(
                        f"Filter cannot output any elements given "
                        f"{[e.name for e in current_types]} as input",
                        filter.token,
                    )
                )
                break
        return current_types

    @property
    def constrained(self) -> Constrained | None:
        constrained: Constrained | None = Constrained.NO
        for filter in self.filters:
            if filter.constrained == Constrained.YES:
                return Constrained.YES
            elif filter.constrained is None:
                constrained = None
        return constrained


# Block Statement Classes


@dataclass
class ForeachStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    body: list[Statement]

    def get_output_types(
        self, warnings: list[QueryWarning]
    ) -> frozenset[ElementType] | None:
        return self.input_set.content_types

    @property
    def constrained(self) -> Constrained | None:
        return self.input_set.constrained


@dataclass
class ForStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    evaluator: Evaluator
    body: list[Statement]

    def get_output_types(
        self, warnings: list[QueryWarning]
    ) -> frozenset[ElementType] | None:
        return self.input_set.content_types

    @property
    def constrained(self) -> Constrained | None:
        return self.input_set.constrained


@dataclass
class CompleteStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    max_iterations: int
    body: list[Statement]

    def get_output_types(
        self, warnings: list[QueryWarning]
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
                        union_result = walk(statement.members, current)
                        if union_result is None:
                            return None
                        current = union_result
                elif isinstance(statement, DifferenceStatement):
                    if statement.output_set.name == accum_name:
                        types = statement.get_output_types(warnings)
                        if types is None:
                            return None
                        current = types
                    else:
                        diff_result = walk(
                            [statement.left_statement, statement.right_statement],
                            current,
                        )
                        if diff_result is None:
                            return None
                        current = diff_result

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

    @property
    def constrained(self) -> Constrained | None:
        if self.input_set.constrained is None:
            return None
        if self.input_set.constrained == Constrained.NO:
            return Constrained.NO

        accum_name = self.input_set.name

        def merge(a: Constrained | None, b: Constrained | None) -> Constrained | None:
            if a == Constrained.NO or b == Constrained.NO:
                return Constrained.NO
            if a is None or b is None:
                return None
            return Constrained.YES

        def walk(
            statements: list[Statement],
            current: Constrained | None,
        ) -> Constrained | None:
            for statement in statements:
                if isinstance(statement, (ForeachStatement, ForStatement)):
                    if statement.output_set.name == accum_name:
                        # loop exit empties the set; empty is trivially constrained
                        current = Constrained.YES
                    else:
                        current = walk(statement.body, current)
                elif isinstance(statement, IfStatement):
                    then_result = walk(statement.then_body, current)
                    else_result = (
                        walk(statement.else_body, current)
                        if statement.else_body
                        else current
                    )
                    current = merge(then_result, else_result)
                elif isinstance(statement, CompleteStatement):
                    if statement.output_set.name == accum_name:
                        current = statement.constrained
                elif isinstance(statement, UnionStatement):
                    if statement.output_set.name == accum_name:
                        current = statement.constrained
                    else:
                        current = walk(statement.members, current)
                elif isinstance(statement, DifferenceStatement):
                    if statement.output_set.name == accum_name:
                        current = statement.constrained
                    else:
                        current = walk(
                            [statement.left_statement, statement.right_statement],
                            current,
                        )
                else:
                    output_set: SetReference | None = getattr(
                        statement, "output_set", None
                    )
                    if output_set is not None and output_set.name == accum_name:
                        current = statement.constrained
            return current

        return walk(self.body, self.input_set.constrained)  # YES at this point


@dataclass
class IfStatement(Statement):
    condition: Evaluator
    then_body: list[Statement]
    else_body: list[Statement] | None

    def get_output_types(
        self, warnings: list[QueryWarning]
    ) -> frozenset[ElementType] | None:
        return _NONE


# Other Statement Classes


@dataclass
class UnionStatement(Statement):
    members: list[Statement]
    output_set: SetReference

    def get_output_types(
        self,
        warnings: list[QueryWarning],
    ) -> frozenset[ElementType] | None:
        result = _NONE
        for member in self.members:
            if isinstance(
                member,
                (OutStatement, ForeachStatement, ForStatement, IfStatement),
            ):
                continue
            member_output_types = member.get_output_types(warnings)
            if member_output_types is None:
                return None
            result = result | member_output_types
        if result == _NONE:
            warnings.append(
                QueryWarning(
                    "Union statement returns no data",
                    None,
                )
            )
        return result

    @property
    def constrained(self) -> Constrained | None:
        constrained: Constrained | None = Constrained.YES
        for member in self.members:
            if member.constrained == Constrained.NO:
                return Constrained.NO
            elif member.constrained is None:
                constrained = None
        return constrained


@dataclass
class DifferenceStatement(Statement):
    left_statement: Statement
    right_statement: Statement
    output_set: SetReference

    def get_output_types(
        self,
        warnings: list[QueryWarning],
    ) -> frozenset[ElementType] | None:
        # propagate None if Phase 2 did not resolve output_types
        if self.right_statement.get_output_types(warnings) is None:
            return None
        return self.left_statement.get_output_types(warnings)

    @property
    def constrained(self) -> Constrained | None:
        if (
            self.left_statement.constrained == Constrained.NO
            or self.right_statement.constrained == Constrained.NO
        ):
            return Constrained.NO
        if (
            self.left_statement.constrained is None
            or self.right_statement.constrained is None
        ):
            return None
        return Constrained.YES


@dataclass
class ItemStatement(Statement):
    input_set: SetReference
    output_set: SetReference

    def get_output_types(
        self, warnings: list[QueryWarning]
    ) -> frozenset[ElementType] | None:
        return self.input_set.content_types

    @property
    def constrained(self) -> Constrained | None:
        return self.input_set.constrained


@dataclass
class OutStatement(Statement):
    input_set: SetReference
    count: bool
    debug: bool
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
        self, warnings: list[QueryWarning]
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

    @property
    def constrained(self) -> Constrained | None:
        return self.input_set.constrained


@dataclass
class IsInStatement(Statement):
    input_set: SetReference
    lat: str | None
    lon: str | None
    output_set: SetReference

    def get_output_types(
        self, warnings: list[QueryWarning]
    ) -> frozenset[ElementType] | None:
        return _AREA

    @property
    def constrained(self) -> Constrained | None:
        return self.input_set.constrained


@dataclass
class MapToAreaStatement(Statement):
    input_set: SetReference
    output_set: SetReference

    def get_output_types(
        self, warnings: list[QueryWarning]
    ) -> frozenset[ElementType] | None:
        return _AREA

    @property
    def constrained(self) -> Constrained | None:
        return self.input_set.constrained


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


# Phase 2 — IR Enrichment
#
# The functions below walk the IR to assign set versions, propagate element
# types through set references, and derive constrained values. They are called
# from the transformer's query() method immediately after Phase 1 (AST → IR
# construction), but have no dependency on Lark internals and could be moved
# to a separate analyzer module. A future analyzer would accept a raw Query
# (fields set by Phase 1, version/content_types/constrained still at defaults)
# and return an enriched Query ready for translation.


_SetState = tuple[int, frozenset[ElementType] | None, Constrained | None]
_State = dict[str, _SetState]

_EMPTY_SET_STATE: _SetState = (0, _NONE, Constrained.YES)


def _stamp_read(ref: SetReference, state: _State, warnings: list[QueryWarning]) -> None:
    if ref.name not in state:
        warnings.append(
            QueryWarning(f"Uninitialized set .{ref.name} contains no data", ref.token)
        )
        state[ref.name] = _EMPTY_SET_STATE
    version, content_types, constrained = state[ref.name]
    ref.version = version
    ref.content_types = content_types
    ref.constrained = constrained
    assert content_types is not None
    if ref.required_types is not None and content_types & ref.required_types == _NONE:
        have = [e.name for e in content_types] if content_types else ["nothing"]
        need = [e.name for e in ref.required_types]
        warnings.append(
            QueryWarning(
                f"Set .{ref.name} contains {have} but requires {need}",
                ref.token,
            )
        )


def _stamp_write(
    ref: SetReference,
    state: _State,
    types: frozenset[ElementType] | None,
    constrained: Constrained | None,
) -> None:
    version = (state[ref.name][0] if ref.name in state else 0) + 1
    state[ref.name] = (version, types, constrained)
    ref.version = version
    ref.content_types = types
    ref.constrained = constrained


def _stamp_evaluator(
    evaluator: Evaluator, state: _State, warnings: list[QueryWarning]
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
    filter_: QueryFilter, state: _State, warnings: list[QueryWarning]
) -> None:
    set_reference: SetReference | None = getattr(filter_, "set_reference", None)
    if set_reference is not None:
        _stamp_read(set_reference, state, warnings)
    elif isinstance(filter_, IfFilter):
        _stamp_evaluator(filter_.evaluator, state, warnings)


def _walk_stmts(
    stmts: list[Statement], state: _State, warnings: list[QueryWarning]
) -> None:
    for stmt in stmts:
        _walk_stmt(stmt, state, warnings)


def _walk_stmt(stmt: Statement, state: _State, warnings: list[QueryWarning]) -> None:
    if isinstance(stmt, IfStatement):
        _walk_if(stmt, state, warnings)
    elif isinstance(stmt, (ForeachStatement, ForStatement)):
        _walk_loop(stmt, state, warnings)
    elif isinstance(stmt, CompleteStatement):
        _walk_complete(stmt, state, warnings)
    elif isinstance(stmt, UnionStatement):
        _walk_union(stmt, state, warnings)
    elif isinstance(stmt, DifferenceStatement):
        _walk_difference(stmt, state, warnings)
    else:
        input_set: SetReference | None = getattr(stmt, "input_set", None)
        if input_set is not None:
            _stamp_read(input_set, state, warnings)
        if isinstance(stmt, QueryStatement):
            for f in stmt.filters:
                _stamp_filter_refs(f, state, warnings)
        output_set: SetReference | None = getattr(stmt, "output_set", None)
        if output_set is not None:
            _stamp_write(
                output_set, state, stmt.get_output_types(warnings), stmt.constrained
            )
    output_set_ref: SetReference | None = getattr(stmt, "output_set", None)
    if output_set_ref is not None and stmt.constrained != Constrained.YES:
        warnings.append(
            QueryWarning(
                "Unconstrained statement may scan the entire planet",
                stmt.token,
            )
        )


def _walk_loop(
    stmt: ForeachStatement | ForStatement,
    state: _State,
    warnings: list[QueryWarning],
) -> None:
    _stamp_read(stmt.input_set, state, warnings)
    if isinstance(stmt, ForStatement):
        _stamp_evaluator(stmt.evaluator, state, warnings)
    _stamp_write(
        stmt.output_set, state, stmt.get_output_types(warnings), stmt.constrained
    )
    _walk_stmts(stmt.body, state, warnings)
    _stamp_write(stmt.output_set, state, _NONE, Constrained.YES)


def _walk_complete(
    stmt: CompleteStatement,
    state: _State,
    warnings: list[QueryWarning],
) -> None:
    _stamp_read(stmt.input_set, state, warnings)
    _stamp_write(
        stmt.output_set, state, stmt.input_set.content_types, stmt.input_set.constrained
    )
    _walk_stmts(stmt.body, state, warnings)
    _stamp_write(
        stmt.output_set, state, stmt.get_output_types(warnings), stmt.constrained
    )


def _walk_union(
    stmt: UnionStatement, state: _State, warnings: list[QueryWarning]
) -> None:
    for member in stmt.members:
        _walk_stmt(member, state, warnings)
    _stamp_write(
        stmt.output_set, state, stmt.get_output_types(warnings), stmt.constrained
    )


def _walk_difference(
    stmt: DifferenceStatement, state: _State, warnings: list[QueryWarning]
) -> None:
    _walk_stmt(stmt.left_statement, state, warnings)
    _walk_stmt(stmt.right_statement, state, warnings)
    _stamp_write(
        stmt.output_set, state, stmt.get_output_types(warnings), stmt.constrained
    )


def _walk_if(stmt: IfStatement, state: _State, warnings: list[QueryWarning]) -> None:
    _stamp_evaluator(stmt.condition, state, warnings)
    then_state = dict(state)
    else_state = dict(state)
    _walk_stmts(stmt.then_body, then_state, warnings)
    _walk_stmts(stmt.else_body or [], else_state, warnings)

    def _written(branch: _State) -> set[str]:
        return {n for n in branch if branch[n][0] > state.get(n, _EMPTY_SET_STATE)[0]}

    written = _written(then_state) | _written(else_state)
    for name in written:
        then_entry = then_state.get(name, state.get(name, _EMPTY_SET_STATE))
        else_entry = else_state.get(name, state.get(name, _EMPTY_SET_STATE))
        then_types, else_types = then_entry[1], else_entry[1]
        if then_types is None or else_types is None:
            merged_types: frozenset[ElementType] | None = None
        else:
            merged_types = then_types | else_types
        then_constrained, else_constrained = then_entry[2], else_entry[2]
        if then_constrained == Constrained.NO or else_constrained == Constrained.NO:
            merged_constrained: Constrained | None = Constrained.NO
        elif then_constrained is None or else_constrained is None:
            merged_constrained = None
        else:
            merged_constrained = Constrained.YES
        version = state.get(name, _EMPTY_SET_STATE)[0] + 1
        state[name] = (version, merged_types, merged_constrained)


def _resolve_types(query: Query) -> None:
    state: _State = {}
    _walk_stmts(query.statements, state, query.warnings)


def _stamp_element_context(evaluator: Evaluator, context: SetReference | None) -> None:
    for f in fields(evaluator):
        val = getattr(evaluator, f.name)
        if f.name == "target_set":
            if val is None and context is not None:
                setattr(evaluator, f.name, context)
        elif isinstance(val, Evaluator):
            # Aggregators establish a new context boundary: their inner evaluator
            # operates on the aggregator's input_set, not the outer context.
            child_context: SetReference | None
            if f.name == "evaluator" and isinstance(
                evaluator, (UniqueEvaluator, MinMaxEvaluator, SumEvaluator)
            ):
                child_context = evaluator.input_set
            else:
                child_context = context
            _stamp_element_context(val, child_context)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, Evaluator):
                    _stamp_element_context(item, context)


def _walk_stmt_element_context(stmt: Statement) -> None:
    if isinstance(stmt, QueryStatement):
        for f in stmt.filters:
            if isinstance(f, IfFilter):
                _stamp_element_context(f.evaluator, stmt.output_set)
    elif isinstance(stmt, ForStatement):
        _stamp_element_context(stmt.evaluator, stmt.input_set)
        for s in stmt.body:
            _walk_stmt_element_context(s)
    elif isinstance(stmt, IfStatement):
        # if_stmt has no element context; walk the condition to reach any
        # nested aggregators that establish their own context boundary.
        _stamp_element_context(stmt.condition, None)
        for s in stmt.then_body:
            _walk_stmt_element_context(s)
        for s in stmt.else_body or []:
            _walk_stmt_element_context(s)
    elif isinstance(stmt, (ForeachStatement, CompleteStatement)):
        for s in stmt.body:
            _walk_stmt_element_context(s)
    elif isinstance(stmt, UnionStatement):
        for member in stmt.members:
            _walk_stmt_element_context(member)
    elif isinstance(stmt, DifferenceStatement):
        _walk_stmt_element_context(stmt.left_statement)
        _walk_stmt_element_context(stmt.right_statement)


def _resolve_element_contexts(query: Query) -> None:
    for stmt in query.statements:
        _walk_stmt_element_context(stmt)


# Overpass Transformer


class OverpassTransformer(Transformer[Token, Query]):
    def __init__(self) -> None:
        super().__init__()
        self.warnings: list[QueryWarning] = []

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
        # Phase 1 ends here. Phase 2 enrichment follows — see the section header
        # above for how these passes could be factored into a separate analyzer.
        _resolve_types(result)
        _resolve_element_contexts(result)
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
            output_types=_ANY,
        )

    def tag_filter_absent(self, children: list[Any]) -> TagKeyFilter:
        return TagKeyFilter(
            key=_unquote(children[0]),
            absent=True,
            token=children[0],
            output_types=_ANY,
        )

    def tag_filter_eq(self, children: list[Any]) -> TagValueFilter:
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.EQ,
            value=_unquote(children[1]),
            case_insensitive=False,
            token=children[0],
            output_types=_ANY,
        )

    def tag_filter_neq(self, children: list[Any]) -> TagValueFilter:
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.NEQ,
            value=_unquote(children[1]),
            case_insensitive=False,
            token=children[0],
            output_types=_ANY,
        )

    def tag_filter_regex(self, children: list[Any]) -> TagValueFilter:
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.REGEX,
            value=_unquote(children[1]),
            case_insensitive=case_insensitive,
            token=children[0],
            output_types=_ANY,
        )

    def tag_filter_not_regex(self, children: list[Any]) -> TagValueFilter:
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.NOT_REGEX,
            value=_unquote(children[1]),
            case_insensitive=case_insensitive,
            token=children[0],
            output_types=_ANY,
        )

    def tag_filter_key_regex(self, children: list[Any]) -> TagValueFilter:
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.KEY_REGEX,
            value=_unquote(children[1]),
            case_insensitive=case_insensitive,
            token=children[0],
            output_types=_ANY,
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
        if float(south) < -90.0 or float(south) > 90.0:
            raise QueryError(
                "Bounding box south latitude out of range [-90, 90]", s_tok
            )
        if float(north) < -90.0 or float(north) > 90.0:
            raise QueryError(
                "Bounding box north latitude out of range [-90, 90]", n_tok
            )
        if float(west) < -180.0 or float(west) > 180.0:
            raise QueryError(
                "Bounding box west longitude out of range [-180, 180]", w_tok
            )
        if float(east) < -180.0 or float(east) > 180.0:
            raise QueryError(
                "Bounding box east longitude out of range [-180, 180]", e_tok
            )
        if float(south) >= float(north):
            self.warnings.append(
                QueryWarning(
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
            output_types=_ANY,
        )

    def id_filter_single(self, children: list[Any]) -> IdFilter:
        assert isinstance(children[0], Token)
        return IdFilter(
            ids=[int(children[0])],
            token=children[0],
            output_types=_ANY,
        )

    def id_filter_list(self, children: list[Any]) -> IdFilter:
        assert isinstance(children[0], Token)
        return IdFilter(
            ids=[int(t) for t in children],
            token=children[0],
            output_types=_ANY,
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
            output_types=_ANY,
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
            output_types=_ANY,
        )

    def around_line_filter(self, children: list[Any]) -> AroundLineFilter:
        radius_token = children[0]
        assert isinstance(radius_token, Token)
        return AroundLineFilter(
            radius=radius_token.value,
            points=list(children[1:]),
            token=radius_token,
            output_types=_ANY,
        )

    def polygon_filter(self, children: list[Any]) -> PolygonFilter:
        assert isinstance(children[0], LatLon)
        return PolygonFilter(
            points=list(children),
            token=children[0].token,
            output_types=_ANY,
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
            return AreaSetFilter(set_reference=ref, token=ref.token, output_types=_ANY)
        return AreaSetFilter(
            set_reference=SetReference(name="_", token=None, required_types=_AREA),
            token=None,
            output_types=_ANY,
        )

    def area_id_filter(self, children: list[Any]) -> AreaIdFilter:
        assert isinstance(children[0], Token)
        return AreaIdFilter(
            area_id=int(children[0]),
            token=children[0],
            output_types=_ANY,
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
            output_types=_ANY,
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
        filter_type = QueryFilterType(str(element_type_tree.data))
        element_types = _ELEMENT_TYPES_MAP[str(element_type_tree.data)]
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
            filter_type=filter_type,
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
        input_set.required_types = _ANY
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
        input_set.required_types = _ANY
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
        max_iterations = 4096
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
        input_set.required_types = _ANY
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

    def union_stmt(self, children: list[Any]) -> UnionStatement:
        members = [c for c in children if isinstance(c, Statement)]
        _FORBIDDEN = (
            OutStatement,
            CompleteStatement,
            ForeachStatement,
            ForStatement,
            IfStatement,
        )
        for member in members:
            if isinstance(member, _FORBIDDEN):
                raise QueryError(
                    f"{type(member).__name__} cannot appear"
                    " as a member of a union statement",
                    member.token,
                )
        output_set = SetReference(name="_", token=None)
        if children and isinstance(children[-1], SetAssignment):
            output_set = children[-1].set_reference
        if members:
            token = members[0].token
        else:
            token = output_set.token
        return UnionStatement(
            members=members,
            output_set=output_set,
            token=token,
        )

    def difference_stmt(self, children: list[Any]) -> DifferenceStatement:
        left_statement = children[0]
        right_statement = children[1]
        assert isinstance(left_statement, Statement)
        assert isinstance(right_statement, Statement)
        output_set = SetReference(name="_", token=None)
        if len(children) == 3:
            assert isinstance(children[2], SetAssignment)
            output_set = children[2].set_reference
        return DifferenceStatement(
            left_statement=left_statement,
            right_statement=right_statement,
            output_set=output_set,
            token=left_statement.token,
        )

    def item_stmt(self, children: list[Any]) -> ItemStatement:
        input_set = children[0]
        assert isinstance(input_set, SetReference)
        input_set.required_types = _ANY
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
        debug_token: Token | None = None
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
                    elif verb == "debug":
                        debug_token = child
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

        # Overpass quirk: `geom` paired with `ids` or `tags` produces bb-only
        # output. Normalize here so the translator only sees true `geom` with
        # skel/body/meta/default verbosity.
        if (
            geom_token is not None
            and verbosity_token is not None
            and str(verbosity_token) in ("ids", "tags")
        ):
            bb_token = geom_token
            geom_token = None

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

        if sort_token is not None and OutSortOrder(str(sort_token)) == OutSortOrder.QT:
            raise UnsupportedFeatureError(
                "Quad tile sorting is not supported", sort_token
            )

        input_set.required_types = _ANY

        return OutStatement(
            input_set=input_set,
            count=count_token is not None,
            debug=debug_token is not None,
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
                QueryWarning(
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
                QueryWarning(
                    "Then branch type is indeterminate and may cause SPARQL errors",
                    children[1].token,
                )
            )
        elif else_type is None:
            output_type = None
            self.warnings.append(
                QueryWarning(
                    "Else branch type is indeterminate and may cause SPARQL errors",
                    children[2].token,
                )
            )
        elif then_type == else_type:
            output_type = then_type
        elif then_type == ScalarType.NUMERIC and else_type == ScalarType.NUMERIC:
            output_type = ScalarType.NUMERIC
        else:
            output_type = None
            self.warnings.append(
                QueryWarning(
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
                    QueryWarning(
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
                    QueryWarning(
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
                QueryWarning(
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
                QueryWarning(
                    "Operand type is indeterminate and may cause SPARQL errors",
                    left_operand.token,
                )
            )
        elif right_type is None:
            self.warnings.append(
                QueryWarning(
                    "Operand type is indeterminate and may cause SPARQL errors",
                    right_operand.token,
                )
            )
        elif left_type != right_type:
            self.warnings.append(
                QueryWarning(
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
        # children: [operand, op, operand, op, operand, ...] (flat from grammar)
        operands: list[Evaluator] = children[0::2]
        operators = [AddOperator(t.value) for t in children[1::2]]

        current_type = operands[0].output_type
        for operator, right_operand in zip(operators, operands[1:]):
            left_type = current_type
            right_type = right_operand.output_type
            if left_type is None or right_type is None:
                token = (
                    right_operand.token if left_type is not None else operands[0].token
                )
                self.warnings.append(
                    QueryWarning(
                        "Operand type is indeterminate and may cause SPARQL errors",
                        token,
                    )
                )
                current_type = None
            elif left_type == ScalarType.NUMERIC and right_type == ScalarType.NUMERIC:
                # numeric addition/subtraction
                current_type = ScalarType.NUMERIC
            elif operator == AddOperator.ADD and (
                left_type == ScalarType.LITERAL or right_type == ScalarType.LITERAL
            ):
                # string concatenation: Overpass concatenates whenever either operand
                # is non-numeric, so one LITERAL side is sufficient
                current_type = ScalarType.LITERAL
            else:
                op_name = (
                    "addition/concatenation"
                    if operator == AddOperator.ADD
                    else "subtraction"
                )
                self.warnings.append(
                    QueryWarning(
                        f"Operand types are incompatible with {op_name}: "
                        f"( {left_type.value} / {right_type.value} )",
                        right_operand.token,
                    )
                )
                current_type = None

        return AddEvaluator(
            operands=operands,
            operators=operators,
            output_type=current_type,
            token=operands[0].token,
        )

    def mul_expr(self, children: list[Any]) -> MultiplyEvaluator:
        # children: [operand, op, operand, op, operand, ...] (flat from grammar)
        operands: list[Evaluator] = children[0::2]
        operators = [MultiplyOperator(t.value) for t in children[1::2]]

        current_type = operands[0].output_type
        for operator, right_operand in zip(operators, operands[1:]):
            left_type = current_type
            right_type = right_operand.output_type
            if left_type is None or right_type is None:
                token = (
                    right_operand.token if left_type is not None else operands[0].token
                )
                self.warnings.append(
                    QueryWarning(
                        "Operand type is indeterminate and may cause SPARQL errors",
                        token,
                    )
                )
                current_type = None
            elif left_type == ScalarType.NUMERIC and right_type == ScalarType.NUMERIC:
                current_type = ScalarType.NUMERIC
            else:
                op_name = (
                    "multiplication"
                    if operator == MultiplyOperator.MULTIPLY
                    else "division"
                )
                self.warnings.append(
                    QueryWarning(
                        f"Operand types are incompatible with {op_name}: "
                        f"( {left_type.value} / {right_type.value} )",
                        right_operand.token,
                    )
                )
                current_type = None

        return MultiplyEvaluator(
            operands=operands,
            operators=operators,
            output_type=current_type,
            token=operands[0].token,
        )

    def unary_expr(self, children: list[Any]) -> UnaryEvaluator:
        operand = children[1]
        assert isinstance(operand, Evaluator)
        operand_type = operand.output_type

        if operand_type is None:
            output_type = None
            self.warnings.append(
                QueryWarning(
                    "Operand type is indeterminate and may cause SPARQL errors",
                    operand.token,
                )
            )
        elif operand_type != ScalarType.NUMERIC:
            output_type = None
            self.warnings.append(
                QueryWarning(
                    "Operand type is incompatible with negation: "
                    f"( {operand_type.value} )",
                    operand.token,
                )
            )
        else:
            output_type = operand_type
        return UnaryEvaluator(
            operator=UnaryOperator.NEGATE,
            operand=children[1],
            output_type=output_type,
            token=children[0],
        )

    def literal_expr(self, children: list[Any]) -> LiteralEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        value = _unquote(token)
        output_type = _infer_literal_type(value)
        return LiteralEvaluator(value=value, output_type=output_type, token=token)

    def id_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(
            attribute=MetadataAttribute(token.value),
            output_type=ScalarType.NUMERIC,
            token=token,
        )

    def type_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(
            attribute=MetadataAttribute(token.value),
            output_type=ScalarType.LITERAL,
            token=token,
        )

    def tag_value_expr(self, children: list[Any]) -> TagValueEvaluator:
        token = children[0].token
        assert isinstance(token, Token)
        evaluator = children[0]
        return TagValueEvaluator(
            evaluator=evaluator, output_type=ScalarType.LITERAL, token=token
        )

    def is_tag_expr(self, children: list[Any]) -> IsTagEvaluator:
        token = children[0]
        key = _unquote(children[0])
        assert isinstance(token, Token)
        return IsTagEvaluator(key=key, output_type=ScalarType.BOOLEAN, token=token)

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
        return MetadataEvaluator(
            attribute=MetadataAttribute(token.value),
            output_type=ScalarType.NUMERIC,
            token=token,
        )

    def timestamp_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(
            attribute=MetadataAttribute(token.value),
            output_type=ScalarType.DATETIME,
            token=token,
        )

    def changeset_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(
            attribute=MetadataAttribute(token.value),
            output_type=ScalarType.NUMERIC,
            token=token,
        )

    def uid_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(
            attribute=MetadataAttribute(token.value),
            output_type=ScalarType.NUMERIC,
            token=token,
        )

    def user_expr(self, children: list[Any]) -> MetadataEvaluator:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataEvaluator(
            attribute=MetadataAttribute(token.value),
            output_type=ScalarType.LITERAL,
            token=token,
        )

    def count_tags_expr(self, children: list[Any]) -> CountTagsEvaluator:
        assert isinstance(children[0], Token)
        return CountTagsEvaluator(output_type=ScalarType.NUMERIC, token=children[0])

    def count_members_expr(self, children: list[Any]) -> CountMembersEvaluator:
        assert isinstance(children[0], Token)
        return CountMembersEvaluator(output_type=ScalarType.NUMERIC, token=children[0])

    def count_distinct_members_expr(self, children: list[Any]) -> CountMembersEvaluator:
        assert isinstance(children[0], Token)
        return CountMembersEvaluator(
            distinct=True, output_type=ScalarType.NUMERIC, token=children[0]
        )

    def count_by_role_expr(self, children: list[Any]) -> CountByRoleEvaluator:
        role = children[0]
        assert isinstance(role, Evaluator)
        return CountByRoleEvaluator(
            role=role, output_type=ScalarType.NUMERIC, token=role.token
        )

    def count_distinct_by_role_expr(self, children: list[Any]) -> CountByRoleEvaluator:
        role = children[0]
        assert isinstance(role, Evaluator)
        return CountByRoleEvaluator(
            role=role, distinct=True, output_type=ScalarType.NUMERIC, token=role.token
        )

    def is_closed_expr(self, children: list[Any]) -> IsClosedEvaluator:
        assert isinstance(children[0], Token)
        return IsClosedEvaluator(output_type=ScalarType.BOOLEAN, token=children[0])

    def lat_expr(self, children: list[Any]) -> CoordinateEvaluator:
        assert isinstance(children[0], Token)
        return CoordinateEvaluator(
            axis=CoordinateAxis.LAT, output_type=ScalarType.NUMERIC, token=children[0]
        )

    def lon_expr(self, children: list[Any]) -> CoordinateEvaluator:
        assert isinstance(children[0], Token)
        return CoordinateEvaluator(
            axis=CoordinateAxis.LON, output_type=ScalarType.NUMERIC, token=children[0]
        )

    def geom_expr(self, children: list[Any]) -> None:
        # geometry can only be assigned to ::geom in convert/make which are unsupported
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("geom() is not supported", children[0])

    def length_expr(self, children: list[Any]) -> LengthEvaluator:
        assert isinstance(children[0], Token)
        return LengthEvaluator(output_type=ScalarType.NUMERIC, token=children[0])

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
        operand = children[0]
        assert isinstance(operand, Evaluator)
        operand_type = operand.output_type

        if operand_type is None:
            self.warnings.append(
                QueryWarning(
                    "Operand type is indeterminate and may not be convertable to a "
                    "number",
                    operand.token,
                )
            )
        elif operand_type != ScalarType.LITERAL and operand_type != ScalarType.NUMERIC:
            self.warnings.append(
                QueryWarning(
                    "Operand may type may not be convertable to a number: "
                    f"( {operand_type.value} )",
                    operand.token,
                )
            )

        return ConversionEvaluator(
            function=ConversionFunction.NUMBER,
            operand=operand,
            output_type=ScalarType.NUMERIC,
            token=children[0].token,
        )

    def date_expr(self, children: list[Any]) -> ConversionEvaluator:
        operand = children[0]
        assert isinstance(operand, Evaluator)
        operand_type = operand.output_type

        if operand_type is None:
            self.warnings.append(
                QueryWarning(
                    "Operand type is indeterminate and may not be convertable to a "
                    "date",
                    operand.token,
                )
            )
        elif operand_type != ScalarType.LITERAL:
            self.warnings.append(
                QueryWarning(
                    "Operand may type may not be convertable to a number: "
                    f"( {operand_type.value} )",
                    operand.token,
                )
            )

        return ConversionEvaluator(
            function=ConversionFunction.DATE,
            operand=operand,
            output_type=ScalarType.DATETIME,
            token=children[0].token,
        )

    def suffix_expr(self, children: list[Any]) -> SuffixEvaluator:
        operand = children[0]
        assert isinstance(operand, Evaluator)
        operand_type = operand.output_type

        if operand_type is None:
            self.warnings.append(
                QueryWarning(
                    "Operand type is indeterminate and may cause SPARQL errors",
                    operand.token,
                )
            )
        elif operand_type != ScalarType.LITERAL:
            self.warnings.append(
                QueryWarning(
                    "Operand may type may cause SPARQL errors: "
                    f"( {operand_type.value} )",
                    operand.token,
                )
            )

        return SuffixEvaluator(
            operand=operand, output_type=ScalarType.LITERAL, token=children[0].token
        )

    def abs_expr(self, children: list[Any]) -> AbsEvaluator:
        operand = children[0]
        assert isinstance(operand, Evaluator)
        operand_type = operand.output_type

        if operand_type is None:
            output_type = None
            self.warnings.append(
                QueryWarning(
                    "Operand type is indeterminate and may cause SPARQL errors",
                    operand.token,
                )
            )
        elif operand_type != ScalarType.NUMERIC:
            output_type = None
            self.warnings.append(
                QueryWarning(
                    "Operand may type is non-numeric and may cause SPARQL errors: "
                    f"( {operand_type.value} )",
                    operand.token,
                )
            )
        else:
            output_type = operand_type

        return AbsEvaluator(
            operand=operand, output_type=output_type, token=children[0].token
        )

    def is_number_expr(self, children: list[Any]) -> TypeCheckEvaluator:
        return TypeCheckEvaluator(
            function=TypeCheckFunction.IS_NUMBER,
            operand=children[0],
            output_type=ScalarType.BOOLEAN,
            token=children[0].token,
        )

    def is_date_expr(self, children: list[Any]) -> TypeCheckEvaluator:
        return TypeCheckEvaluator(
            function=TypeCheckFunction.IS_DATE,
            operand=children[0],
            output_type=ScalarType.BOOLEAN,
            token=children[0].token,
        )

    def unique_expr(self, children: list[Any]) -> UniqueEvaluator:
        evaluator = children[-1]
        assert isinstance(evaluator, Evaluator)
        evaluator_type = evaluator.output_type

        if evaluator_type is None:
            self.warnings.append(
                QueryWarning(
                    "Expression type is indeterminate and may cause SPARQL errors",
                    evaluator.token,
                )
            )

        if len(children) == 2:
            set_reference = children[0]
        else:
            set_reference = SetReference(name="_", token=None)

        return UniqueEvaluator(
            input_set=set_reference,
            output_type=ScalarType.LITERAL,
            evaluator=evaluator,
            token=evaluator.token,
        )

    def min_expr(self, children: list[Any]) -> MinMaxEvaluator:
        evaluator = children[-1]
        assert isinstance(evaluator, Evaluator)
        evaluator_type = evaluator.output_type

        if evaluator_type is None:
            self.warnings.append(
                QueryWarning(
                    "Expression type is indeterminate and may cause SPARQL errors",
                    evaluator.token,
                )
            )

        if len(children) == 2:
            set_reference = children[0]
        else:
            set_reference = SetReference(name="_", token=None)

        return MinMaxEvaluator(
            input_set=set_reference,
            operator=AggregateOperator.MIN,
            output_type=evaluator_type,
            evaluator=evaluator,
            token=evaluator.token,
        )

    def max_expr(self, children: list[Any]) -> MinMaxEvaluator:
        evaluator = children[-1]
        assert isinstance(evaluator, Evaluator)
        evaluator_type = evaluator.output_type

        if evaluator_type is None:
            self.warnings.append(
                QueryWarning(
                    "Expression type is indeterminate and may cause SPARQL errors",
                    evaluator.token,
                )
            )

        if len(children) == 2:
            set_reference = children[0]
        else:
            set_reference = SetReference(name="_", token=None)

        return MinMaxEvaluator(
            input_set=set_reference,
            operator=AggregateOperator.MAX,
            output_type=evaluator_type,
            evaluator=evaluator,
            token=evaluator.token,
        )

    def sum_expr(self, children: list[Any]) -> SumEvaluator:
        evaluator = children[-1]
        assert isinstance(evaluator, Evaluator)
        evaluator_type = evaluator.output_type

        if evaluator_type is None:
            output_type = None
            self.warnings.append(
                QueryWarning(
                    "Expression type is indeterminate and may cause SPARQL errors",
                    evaluator.token,
                )
            )
        elif evaluator_type != ScalarType.NUMERIC:
            output_type = None
            self.warnings.append(
                QueryWarning(
                    "Expression type is non-numeric and may cause SPARQL errors: "
                    f"( {evaluator_type.value} )",
                    evaluator.token,
                )
            )
        else:
            output_type = ScalarType.NUMERIC

        if len(children) == 2:
            set_reference = children[0]
        else:
            set_reference = SetReference(name="_", token=None)

        return SumEvaluator(
            input_set=set_reference,
            evaluator=evaluator,
            output_type=output_type,
            token=evaluator.token,
        )

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
            output_type=ScalarType.NUMERIC,
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
        # TODO: validate in a semantic pass — walk the IR with a stack of for loop
        # output set names; raise if set_reference.name matches none of them.
        # TODO: carry the output type of the for loop evaluator down to this
        # evaluator's output type
        set_reference = children[0]
        assert isinstance(set_reference, SetReference)
        assert set_reference.token is not None
        return ValEvaluator(
            set_reference=set_reference, output_type=None, token=set_reference.token
        )


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
