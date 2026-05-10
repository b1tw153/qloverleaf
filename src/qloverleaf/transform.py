import re
from dataclasses import dataclass, field
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
    token: Token


# Basic Types


class ElementType(Enum):
    NODE = "node"
    WAY = "way"
    RELATION = "relation"
    AREA = "area"
    # TODO: verify which filters accept derived elements as input or output;
    # derived elements may have geometry but are not expected in the POC
    DERIVED = "derived"


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


# Set Reference


@dataclass
class SetReference:
    name: str  # canonical name; "_" if implicit
    token: Token | None  # None if implicit
    versioned: str = ""  # filled in by SSA phase
    # None = no constraint on what types the set must contain
    required_types: frozenset[ElementType] | None = field(default=None)


# Set Assignment


@dataclass
class SetAssignment:
    set_ref: SetReference


_NODE = frozenset({ElementType.NODE})
_WAY = frozenset({ElementType.WAY})
_RELATION = frozenset({ElementType.RELATION})
_AREA = frozenset({ElementType.AREA})
_NWR = frozenset({ElementType.NODE, ElementType.WAY, ElementType.RELATION})
_WR = frozenset({ElementType.WAY, ElementType.RELATION})
_NW = frozenset({ElementType.NODE, ElementType.WAY})
_NR = frozenset({ElementType.NODE, ElementType.RELATION})

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


# Evaluator Classes


@dataclass(kw_only=True)
class Evaluator:
    token: Token


@dataclass
class TernaryExpression(Evaluator):
    condition: Evaluator
    true_expression: Evaluator
    false_expression: Evaluator


@dataclass
class BinaryExpression(Evaluator):
    operator: BinaryOperator
    operands: list[Evaluator]


@dataclass
class UnaryExpression(Evaluator):
    operator: UnaryOperator
    operand: Evaluator


@dataclass
class CompareExpression(Evaluator):
    left_operand: Evaluator
    operator: CompareOperator
    right_operand: Evaluator


@dataclass
class AddExpression(Evaluator):
    left_operand: Evaluator
    operator: AddOperator
    right_operand: Evaluator


@dataclass
class MultiplyExpression(Evaluator):
    left_operand: Evaluator
    operator: MultiplyOperator
    right_operand: Evaluator


# ...


@dataclass
class LiteralExpression(Evaluator):
    value: str


@dataclass
class MetadataExpression(Evaluator):
    attribute: MetadataAttribute


@dataclass
class TagValueExpression(Evaluator):
    evaluator: LiteralExpression


@dataclass
class IsTagExpression(Evaluator):
    key: str


@dataclass
class CoordinateExpression(Evaluator):
    axis: CoordinateAxis


@dataclass
class ConversionExpression(Evaluator):
    function: ConversionFunction
    operand: Evaluator


@dataclass
class SuffixExpression(Evaluator):
    operand: Evaluator


@dataclass
class AbsExpression(Evaluator):
    operand: Evaluator


@dataclass
class TypeCheckExpression(Evaluator):
    function: TypeCheckFunction
    operand: Evaluator


@dataclass
class IsClosedExpression(Evaluator):
    pass


@dataclass
class LengthExpression(Evaluator):
    pass


@dataclass
class CountExpression(Evaluator):
    count_type: CountType
    set_ref: SetReference


@dataclass
class ValExpression(Evaluator):
    set_ref: SetReference


# Query Filter Classes


@dataclass(kw_only=True)
class QueryFilter:
    token: Token | None  # None when set_ref is implicit
    input_types: frozenset[ElementType] | None = field(default=None)
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
    set_ref: SetReference


@dataclass
class AroundPointFilter(QueryFilter):
    radius: str
    lat: str
    lon: str


@dataclass
class AroundLineFilter(QueryFilter):
    radius: str
    points: list[tuple[str, str]]


@dataclass
class PolygonFilter(QueryFilter):
    points: list[tuple[str, str]]


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
    set_ref: SetReference


@dataclass
class AreaIdFilter(QueryFilter):
    area_id: int


@dataclass
class RecurseFilter(QueryFilter):
    recurse_type: RecurseFilterType
    set_ref: SetReference
    role: str | None


@dataclass
class WayCountFilter(QueryFilter):
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


# Simple Statement Classes


@dataclass(kw_only=True)
class Statement:
    token: Token | None


@dataclass
class QueryStatement(Statement):
    element_types: frozenset[ElementType]
    filters: list[QueryFilter]
    output_set: SetReference


# Block Statement Classes


@dataclass
class ForeachStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    body: list[Any]


@dataclass
class ForStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    evaluator: Evaluator
    body: list[Any]


@dataclass
class CompleteStatement(Statement):
    input_set: SetReference
    output_set: SetReference
    max_iterations: int | None
    body: list[Any]


@dataclass
class IfStatement(Statement):
    condition: Evaluator
    then_body: list[Any]
    else_body: list[Any] | None


# Other Statement Classes


@dataclass
class UnionMember:
    difference: bool
    statement: Statement


@dataclass
class UnionStatement(Statement):
    members: list[UnionMember]
    output_set: SetReference


@dataclass
class ItemStatement(Statement):
    input_set: SetReference
    output_set: SetReference


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


@dataclass
class IsInStatement(Statement):
    input_set: SetReference
    lat: str | None
    lon: str | None
    output_set: SetReference


@dataclass
class MapToAreaStatement(Statement):
    input_set: SetReference
    output_set: SetReference


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


# Overpass Transformer


class OverpassTransformer(Transformer[Token, Any]):
    def __init__(self) -> None:
        super().__init__()
        self.warnings: list[Warning] = []

    def transform(self, tree: Tree[Token]) -> Any:
        try:
            return super().transform(tree)
        except VisitError as e:
            raise e.orig_exc from e

    # Global Settings

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

    def around_lat_lon(self, children: list[Any]) -> tuple[str, str]:
        lat_tok, lon_tok = children
        assert isinstance(lat_tok, Token)
        assert isinstance(lon_tok, Token)
        return (lat_tok.value, lon_tok.value)

    def poly_lat_lon(self, children: list[Any]) -> tuple[str, str, Token]:
        lat_tok, lon_tok = children
        assert isinstance(lat_tok, Token)
        assert isinstance(lon_tok, Token)
        return (lat_tok.value, lon_tok.value, lat_tok)

    def set_ref(self, children: list[Any]) -> SetReference:
        assert isinstance(children[0], Token)
        return SetReference(
            name=str(children[0]),
            token=children[0],
        )

    def recurse_role(self, children: list[Any]) -> str:
        assert isinstance(children[0], Token)
        return _unquote(children[0])

    def int_range(self, children: list[Any]) -> tuple[int, int | None, bool, Token]:
        assert isinstance(children[0], Token)
        if len(children) == 1:
            return (int(children[0]), int(children[0]), True, children[0])
        elif len(children) == 2:
            return (int(children[0]), None, False, children[0])
        else:
            assert isinstance(children[2], Token)
            return (int(children[0]), int(children[2]), False, children[0])

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
        )

    def tag_filter_absent(self, children: list[Any]) -> TagKeyFilter:
        return TagKeyFilter(
            key=_unquote(children[0]),
            absent=True,
            token=children[0],
        )

    def tag_filter_eq(self, children: list[Any]) -> TagValueFilter:
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.EQ,
            value=_unquote(children[1]),
            case_insensitive=False,
            token=children[0],
        )

    def tag_filter_neq(self, children: list[Any]) -> TagValueFilter:
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.NEQ,
            value=_unquote(children[1]),
            case_insensitive=False,
            token=children[0],
        )

    def tag_filter_regex(self, children: list[Any]) -> TagValueFilter:
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.REGEX,
            value=_unquote(children[1]),
            case_insensitive=case_insensitive,
            token=children[0],
        )

    def tag_filter_not_regex(self, children: list[Any]) -> TagValueFilter:
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(children[0]),
            op=TagFilterOp.NOT_REGEX,
            value=_unquote(children[1]),
            case_insensitive=case_insensitive,
            token=children[0],
        )

    def tag_filter_key_regex(self, children: list[Any]) -> None:
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
        )

    def id_filter_single(self, children: list[Any]) -> IdFilter:
        assert isinstance(children[0], Token)
        return IdFilter(
            ids=[int(children[0])],
            token=children[0],
        )

    def id_filter_list(self, children: list[Any]) -> IdFilter:
        assert isinstance(children[0], Token)
        return IdFilter(
            ids=[int(t) for t in children],
            token=children[0],
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
            set_ref=set_reference,
            token=radius_token,
        )

    def around_point_filter(self, children: list[Any]) -> AroundPointFilter:
        radius_token, (lat, lon) = children[0], children[1]
        assert isinstance(radius_token, Token)
        return AroundPointFilter(
            radius=radius_token.value,
            lat=lat,
            lon=lon,
            token=radius_token,
        )

    def around_line_filter(self, children: list[Any]) -> AroundLineFilter:
        radius_token = children[0]
        assert isinstance(radius_token, Token)
        return AroundLineFilter(
            radius=radius_token.value,
            points=list(children[1:]),
            token=radius_token,
        )

    def polygon_filter(self, children: list[Any]) -> PolygonFilter:
        first_token = children[0][2]
        assert isinstance(first_token, Token)
        return PolygonFilter(
            points=[(lat, lon) for lat, lon, _ in children],
            token=first_token,
        )

    def newer_filter(self, children: list[Any]) -> NewerFilter:
        assert isinstance(children[0], Token)
        return NewerFilter(timestamp=_parse_datetime(children[0]), token=children[0])

    def changed_filter(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("changed filter is not supported", children[0])

    def user_filter(self, children: list[Any]) -> UserFilter:
        assert isinstance(children[0], Token)
        return UserFilter(users=[_unquote(t) for t in children], token=children[0])

    def uid_filter(self, children: list[Any]) -> UidFilter:
        assert isinstance(children[0], Token)
        return UidFilter(uids=[int(t) for t in children], token=children[0])

    def user_touched_filter(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError(
            "user_touched filter is not supported", children[0]
        )

    def uid_touched_filter(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError(
            "uid_touched filter is not supported", children[0]
        )

    def area_set_filter(self, children: list[Any]) -> AreaSetFilter:
        if children:
            ref = children[0]
            assert isinstance(ref, SetReference)
            ref.required_types = _AREA
            return AreaSetFilter(set_ref=ref, token=ref.token)
        return AreaSetFilter(
            set_ref=SetReference(name="_", token=None, required_types=_AREA),
            token=None,
        )

    def area_id_filter(self, children: list[Any]) -> AreaIdFilter:
        assert isinstance(children[0], Token)
        return AreaIdFilter(
            area_id=int(children[0]),
            token=children[0],
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
                input_types: frozenset[ElementType] | None = _WR
                output_types: frozenset[ElementType] | None = _WR
            case RecurseFilterType.BW:
                set_reference.required_types = _WAY
                input_types = _RELATION
                output_types = _RELATION
            case RecurseFilterType.BR:
                set_reference.required_types = _RELATION
                input_types = _RELATION
                output_types = _RELATION
            case RecurseFilterType.W:
                set_reference.required_types = _WAY
                input_types = _NODE
                output_types = _NODE
            case RecurseFilterType.R:
                set_reference.required_types = _RELATION
                input_types = _NWR
                output_types = _NWR
        return RecurseFilter(
            recurse_type=recurse_type,
            set_ref=set_reference,
            role=role,
            token=type_token,
            input_types=input_types,
            output_types=output_types,
        )

    def way_count_filter(self, children: list[Any]) -> WayCountFilter:
        min_count, max_count, exact, token = children[0]
        return WayCountFilter(
            min_count=min_count,
            max_count=max_count,
            exact=exact,
            token=token,
            input_types=_WAY,
            output_types=_NODE,
        )

    def way_link_filter(self, children: list[Any]) -> None:
        min_count, max_count, exact, token = children[0]
        raise UnsupportedFeatureError("way_link filter is not supported", token)

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
                input_types=_WR,
                output_types=_WR,
            )
        return PivotFilter(
            set_reference=SetReference(name="_", token=None, required_types=_AREA),
            input_types=_WR,
            output_types=_WR,
            token=None,
        )

    def if_filter(self, children: list[Any]) -> IfFilter:
        evaluator = children[0]
        assert isinstance(evaluator, Evaluator)
        return IfFilter(
            evaluator=evaluator,
            token=evaluator.token,
        )

    def set_assignment(self, children: list[Any]) -> SetAssignment:
        assert isinstance(children[0], SetReference)
        return SetAssignment(set_ref=children[0])

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
                output_set = child.set_ref
        output_set.required_types = element_types
        # TODO: walk filters to propagate input/output type constraints
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
                output_set = child.set_ref
            elif isinstance(child, list):
                body = child
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
                output_set = child.set_ref
            elif isinstance(child, Evaluator):
                evaluator = child
            elif isinstance(child, list):
                body = child
        assert evaluator is not None
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
                output_set = child.set_ref
            elif isinstance(child, Token) and child.type == "INTEGER":
                max_iterations = int(child)
            else:
                body.append(child)
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
        # TODO: validate that no member is a foreach_stmt or out_stmt — wiki says
        # these cannot appear as sub-elements of a union (raise QueryError if found);
        # requires a full recursive walk of the member subtree
        members: list[UnionMember] = children[0]
        output_set = SetReference(name="_", token=None)
        if len(children) == 2:
            assert isinstance(children[1], SetAssignment)
            output_set = children[1].set_ref
        # TODO: use members[0].statement.token once statement production is handled
        # if members:
        #     token = members[0].statement.token
        # else:
        token = output_set.token
        return UnionStatement(
            members=members,
            output_set=output_set,
            token=token,
        )

    def item_stmt(self, children: list[Any]) -> ItemStatement:
        input_set = children[0]
        assert isinstance(input_set, SetReference)
        output_set = SetReference(name="_", token=None)
        if len(children) == 2:
            assert isinstance(children[1], SetAssignment)
            output_set = children[1].set_ref
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
                    "bbox_filter in out statement is not supported", child.token
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
                output_set = child.set_ref
            elif isinstance(child, Token) and child.type == "RECURSE_DIR":
                recurse_dir = RecurseDir(child.value)
                token = child if token is None else token
        assert recurse_dir is not None
        match recurse_dir:
            case RecurseDir.DOWN:
                input_set.required_types = _NWR
                output_set.required_types = _NW
            case RecurseDir.DOWN_RELATIONS:
                input_set.required_types = _NWR
                output_set.required_types = _NWR
            case RecurseDir.UP | RecurseDir.UP_RELATIONS:
                input_set.required_types = _NWR
                output_set.required_types = _WR
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
                output_set = child.set_ref
                token = child.set_ref.token if token is None else token
        input_set.required_types = _NODE
        output_set.required_types = _AREA
        return IsInStatement(
            input_set=input_set,
            lat=lat,
            lon=lon,
            output_set=output_set,
            token=token,
        )

    def timeline_stmt(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError(
            "timeline statement is not supported", children[0]
        )

    def local_stmt(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError(
            "local statement is not supported", children[0] if children else None
        )

    def convert_stmt(self, children: list[Any]) -> None:
        raise UnimplementedFeatureError(
            "convert statement is not implemented", children[0]
        )

    def make_stmt(self, children: list[Any]) -> None:
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
                output_set = child.set_ref
                output_set.required_types = _AREA
                token = child.set_ref.token if token is None else token
        return MapToAreaStatement(
            input_set=input_set,
            output_set=output_set,
            token=token,
        )

    def compare_stmt(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError(
            "compare statement is not supported",
            children[0] if children else None,
        )

    # Evaluator Transforms

    def ternary_expr(self, children: list[Any]) -> TernaryExpression:
        return TernaryExpression(
            condition=children[0],
            true_expression=children[1],
            false_expression=children[2],
            token=children[0].token,
        )

    def or_expr(self, children: list[Any]) -> BinaryExpression:
        return BinaryExpression(
            operator=BinaryOperator.OR, operands=children, token=children[0].token
        )

    def and_expr(self, children: list[Any]) -> BinaryExpression:
        return BinaryExpression(
            operator=BinaryOperator.AND, operands=children, token=children[0].token
        )

    def not_expr(self, children: list[Any]) -> UnaryExpression:
        return UnaryExpression(
            operator=UnaryOperator.NOT, operand=children[1], token=children[0]
        )

    def compare_expr(self, children: list[Any]) -> CompareExpression:
        return CompareExpression(
            left_operand=children[0],
            operator=CompareOperator(children[1].value),
            right_operand=children[2],
            token=children[0].token,
        )

    def add_expr(self, children: list[Any]) -> AddExpression:
        return AddExpression(
            left_operand=children[0],
            operator=AddOperator(children[1].value),
            right_operand=children[2],
            token=children[0].token,
        )

    def mul_expr(self, children: list[Any]) -> MultiplyExpression:
        return MultiplyExpression(
            left_operand=children[0],
            operator=MultiplyOperator(children[1].value),
            right_operand=children[2],
            token=children[0].token,
        )

    def unary_expr(self, children: list[Any]) -> UnaryExpression:
        return UnaryExpression(
            operator=UnaryOperator.NEGATE,
            operand=children[1],
            token=children[0],
        )

    def literal_expr(self, children: list[Any]) -> LiteralExpression:
        token = children[0]
        assert isinstance(token, Token)
        return LiteralExpression(value=_unquote(token), token=token)

    def id_expr(self, children: list[Any]) -> MetadataExpression:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataExpression(attribute=MetadataAttribute(token.value), token=token)

    def type_expr(self, children: list[Any]) -> MetadataExpression:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataExpression(attribute=MetadataAttribute(token.value), token=token)

    def tag_value_expr(self, children: list[Any]) -> TagValueExpression:
        token = children[0].token
        assert isinstance(token, Token)
        evaluator = children[0]
        if not isinstance(evaluator, LiteralExpression):
            raise UnsupportedFeatureError(
                "t[...] with a dynamic key expression is not supported", token
            )
        return TagValueExpression(evaluator=evaluator, token=token)

    def is_tag_expr(self, children: list[Any]) -> IsTagExpression:
        token = children[0]
        key = _unquote(children[0])
        assert isinstance(token, Token)
        return IsTagExpression(key=key, token=token)

    def keys_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("keys() evaluator is not supported", children[0])

    # generic_tag_expr - implemented only in the context of convert/make

    def version_expr(self, children: list[Any]) -> MetadataExpression:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataExpression(attribute=MetadataAttribute(token.value), token=token)

    def timestamp_expr(self, children: list[Any]) -> MetadataExpression:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataExpression(attribute=MetadataAttribute(token.value), token=token)

    def changeset_expr(self, children: list[Any]) -> MetadataExpression:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataExpression(attribute=MetadataAttribute(token.value), token=token)

    def uid_expr(self, children: list[Any]) -> MetadataExpression:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataExpression(attribute=MetadataAttribute(token.value), token=token)

    def user_expr(self, children: list[Any]) -> MetadataExpression:
        token = children[0]
        assert isinstance(token, Token)
        return MetadataExpression(attribute=MetadataAttribute(token.value), token=token)

    def count_tags_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnimplementedFeatureError("count_tags() is not implemented", children[0])

    def count_members_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnimplementedFeatureError(
            "count_members() is not implemented", children[0]
        )

    def count_distinct_members_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnimplementedFeatureError(
            "count_distinct_members() is not implemented", children[0]
        )

    def count_by_role_expr(self, children: list[Any]) -> None:
        raise UnimplementedFeatureError(
            "count_by_role() is not implemented", children[0].token
        )

    def count_distinct_by_role_expr(self, children: list[Any]) -> None:
        raise UnimplementedFeatureError(
            "count_distinct_by_role() is not implemented", children[0].token
        )

    def is_closed_expr(self, children: list[Any]) -> IsClosedExpression:
        assert isinstance(children[0], Token)
        return IsClosedExpression(token=children[0])

    def lat_expr(self, children: list[Any]) -> CoordinateExpression:
        assert isinstance(children[0], Token)
        return CoordinateExpression(axis=CoordinateAxis.LAT, token=children[0])

    def lon_expr(self, children: list[Any]) -> CoordinateExpression:
        assert isinstance(children[0], Token)
        return CoordinateExpression(axis=CoordinateAxis.LON, token=children[0])

    def geom_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("geom() is not supported", children[0])

    def length_expr(self, children: list[Any]) -> LengthExpression:
        assert isinstance(children[0], Token)
        return LengthExpression(token=children[0])

    def center_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("center() is not supported", children[0].token)

    def trace_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("trace() is not supported", children[0].token)

    def hull_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("hull() is not supported", children[0].token)

    def pt_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("pt() is not supported", children[0].token)

    def lstr_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("lstr() is not supported", children[0].token)

    def poly_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("poly() is not supported", children[0].token)

    def per_member_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError(
            "per_member() is not supported", children[0].token
        )

    def per_vertex_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError(
            "per_vertex() is not supported", children[0].token
        )

    def pos_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("pos() is not supported", children[0])

    def mtype_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("mtype() is not supported", children[0])

    def ref_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("ref() is not supported", children[0])

    def role_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("role() is not supported", children[0])

    def angle_expr(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError("angle() is not supported", children[0])

    def number_expr(self, children: list[Any]) -> ConversionExpression:
        return ConversionExpression(
            function=ConversionFunction.NUMBER,
            operand=children[0],
            token=children[0].token,
        )

    def date_expr(self, children: list[Any]) -> ConversionExpression:
        return ConversionExpression(
            function=ConversionFunction.DATE,
            operand=children[0],
            token=children[0].token,
        )

    def suffix_expr(self, children: list[Any]) -> SuffixExpression:
        return SuffixExpression(operand=children[0], token=children[0].token)

    def abs_expr(self, children: list[Any]) -> AbsExpression:
        return AbsExpression(operand=children[0], token=children[0].token)

    def is_number_expr(self, children: list[Any]) -> TypeCheckExpression:
        return TypeCheckExpression(
            function=TypeCheckFunction.IS_NUMBER,
            operand=children[0],
            token=children[0].token,
        )

    def is_date_expr(self, children: list[Any]) -> TypeCheckExpression:
        return TypeCheckExpression(
            function=TypeCheckFunction.IS_DATE,
            operand=children[0],
            token=children[0].token,
        )

    def unique_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("u() is not supported", children[0].token)

    def min_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("min() is not supported", children[0].token)

    def max_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("max() is not supported", children[0].token)

    def sum_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("sum() is not supported", children[0].token)

    def set_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("set() is not supported", children[0].token)

    def gcat_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("gcat() is not supported", children[0].token)

    def count_expr(self, children: list[Any]) -> CountExpression:
        count_type_token = children[-1]
        assert isinstance(count_type_token, Token)
        if len(children) == 2:
            set_ref = children[0]
        else:
            set_ref = SetReference(name="_", token=None)
        count_type = CountType(str(count_type_token))
        if count_type == CountType.DERIVEDS:
            raise UnsupportedFeatureError(
                "count(deriveds) is not supported", count_type_token
            )
        return CountExpression(
            count_type=count_type,
            set_ref=set_ref,
            token=count_type_token,
        )

    def lrs_in_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("lrs_in() is not supported", children[0].token)

    def lrs_isect_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("lrs_isect() is not supported", children[0].token)

    def lrs_union_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("lrs_union() is not supported", children[0].token)

    def lrs_min_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("lrs_min() is not supported", children[0].token)

    def lrs_max_expr(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError("lrs_max() is not supported", children[0].token)

    def val_expr(self, children: list[Any]) -> ValExpression:
        # set_ref must be the output set of an enclosing for_stmt (sets are global,
        # so any for loop on the stack is valid, not just the innermost). Only that
        # set is populated with per-iteration values.
        # TODO: validate in a semantic pass — walk the IR with a stack of for loop
        # output set names; raise if set_ref.name matches none of them.
        set_ref = children[0]
        assert isinstance(set_ref, SetReference)
        assert set_ref.token is not None
        return ValExpression(set_ref=set_ref, token=set_ref.token)
