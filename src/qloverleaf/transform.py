import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from lark import Token, Transformer, Tree
from lark.exceptions import VisitError

from qloverleaf.exceptions import UnsupportedFeatureError


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


# Set Reference

@dataclass
class SetReference:
    name: str                                    # canonical name; "._" if implicit
    token: Token | None                          # None if implicit
    versioned: str = ""                          # filled in by SSA phase
    # None = no constraint on what types the set must contain
    required_types: frozenset[ElementType] | None = field(default=None)


_NODES = frozenset({ElementType.NODE})
_WAYS = frozenset({ElementType.WAY})
_RELATIONS = frozenset({ElementType.RELATION})
_AREAS = frozenset({ElementType.AREA})
_NON_AREA = frozenset({ElementType.NODE, ElementType.WAY, ElementType.RELATION})
_WR = frozenset({ElementType.WAY, ElementType.RELATION})


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


# ...

@dataclass
class LiteralExpression(Evaluator):
    value: str


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
    south: float
    west: float
    north: float
    east: float


@dataclass
class IdFilter(QueryFilter):
    ids: list[int]


@dataclass
class AroundSetFilter(QueryFilter):
    radius: float
    set_ref: SetReference


@dataclass
class AroundPointFilter(QueryFilter):
    radius: float
    lat: float
    lon: float


@dataclass
class AroundLineFilter(QueryFilter):
    radius: float
    points: list[tuple[float, float]]


@dataclass
class PolygonFilter(QueryFilter):
    points: list[tuple[float, float]]


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
    exact: bool            # True if no dash (exact match)


@dataclass
class SetFilter(QueryFilter):
    set_ref: SetReference


@dataclass
class PivotFilter(QueryFilter):
    set_ref: SetReference


@dataclass
class IfFilter(QueryFilter):
    evaluator: Evaluator


# Helper Functions

def _parse_datetime(token: Token) -> datetime:
    v = str(token)
    if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
        v = v[1:-1]
    return datetime.fromisoformat(v)


_ESCAPE_MAP = {'n': '\n', 't': '\t', '"': '"', "'": "'", '\\': '\\'}


def _unquote(token: Token) -> str:
    v = str(token)
    if len(v) < 2 or v[0] not in ('"', "'") or v[-1] != v[0]:
        return v
    inner = v[1:-1]

    def replace_escape(m: re.Match) -> str:  # type: ignore[type-arg]
        seq = m.group(1)
        if seq[0] == 'u':
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

    # Basic Type Transforms

    def tag_key(self, children: list[Any]) -> Token:
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

    def number(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

    def around_radius(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

    def around_lat_lon(self, children: list[Any]) -> tuple[float, float]:
        lat_tok, lon_tok = children
        assert isinstance(lat_tok, Token)
        assert isinstance(lon_tok, Token)
        return (float(lat_tok), float(lon_tok))

    def poly_lat_lon(self, children: list[Any]) -> tuple[float, float, Token]:
        lat_tok, lon_tok = children
        assert isinstance(lat_tok, Token)
        assert isinstance(lon_tok, Token)
        return (float(lat_tok), float(lon_tok), lat_tok)

    def set_ref(self, children: list[Any]) -> SetReference:
        assert isinstance(children[0], Token)
        return SetReference(name=str(children[0]), token=children[0])

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

    # Query Filter Transforms

    def tag_filter_exists(self, children: list[Any]) -> TagKeyFilter:
        key_token = children[0]
        return TagKeyFilter(key=_unquote(key_token), absent=False, token=key_token)

    def tag_filter_absent(self, children: list[Any]) -> TagKeyFilter:
        key_token = children[0]
        return TagKeyFilter(key=_unquote(key_token), absent=True, token=key_token)

    def tag_filter_eq(self, children: list[Any]) -> TagValueFilter:
        key_token, value_token = children[0], children[1]
        return TagValueFilter(
            key=_unquote(key_token),
            op=TagFilterOp.EQ,
            value=_unquote(value_token),
            case_insensitive=False,
            token=key_token,
        )

    def tag_filter_neq(self, children: list[Any]) -> TagValueFilter:
        key_token, value_token = children[0], children[1]
        return TagValueFilter(
            key=_unquote(key_token),
            op=TagFilterOp.NEQ,
            value=_unquote(value_token),
            case_insensitive=False,
            token=key_token,
        )

    def tag_filter_regex(self, children: list[Any]) -> TagValueFilter:
        key_token, value_token = children[0], children[1]
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(key_token),
            op=TagFilterOp.REGEX,
            value=_unquote(value_token),
            case_insensitive=case_insensitive,
            token=key_token,
        )

    def tag_filter_not_regex(self, children: list[Any]) -> TagValueFilter:
        key_token, value_token = children[0], children[1]
        case_insensitive = len(children) > 2 and children[2] is True
        return TagValueFilter(
            key=_unquote(key_token),
            op=TagFilterOp.NOT_REGEX,
            value=_unquote(value_token),
            case_insensitive=case_insensitive,
            token=key_token,
        )

    def tag_filter_key_regex(self, children: list[Any]) -> None:
        raise UnsupportedFeatureError(
            "Key regex filter [~key~value] is not supported", children[0]
        )

    def bbox_filter(self, children: list[Any]) -> BboxFilter:
        s_tok, w_tok, n_tok, e_tok = children
        assert isinstance(s_tok, Token)
        south, west, north, east = (
            float(s_tok), float(w_tok), float(n_tok), float(e_tok)
        )
        if south >= north:
            self.warnings.append(Warning(
                "Bounding box south >= north: filter will always be empty",
                s_tok,
            ))
        return BboxFilter(
            south=south, west=west, north=north, east=east, token=s_tok
        )

    def id_filter_single(self, children: list[Any]) -> IdFilter:
        assert isinstance(children[0], Token)
        return IdFilter(ids=[int(children[0])], token=children[0])

    def id_filter_list(self, children: list[Any]) -> IdFilter:
        assert isinstance(children[0], Token)
        return IdFilter(ids=[int(t) for t in children], token=children[0])

    def around_set_filter(self, children: list[Any]) -> AroundSetFilter:
        if len(children) == 1:
            ref = SetReference(name="._", token=None, required_types=_NON_AREA)
            radius_tok = children[0]
        else:
            ref, radius_tok = children[0], children[1]
            ref.required_types = _NON_AREA
        assert isinstance(radius_tok, Token)
        return AroundSetFilter(
            radius=float(radius_tok), set_ref=ref, token=radius_tok
        )

    def around_point_filter(self, children: list[Any]) -> AroundPointFilter:
        radius_tok, (lat, lon) = children[0], children[1]
        assert isinstance(radius_tok, Token)
        return AroundPointFilter(
            radius=float(radius_tok), lat=lat, lon=lon, token=radius_tok
        )

    def around_line_filter(self, children: list[Any]) -> AroundLineFilter:
        radius_tok = children[0]
        assert isinstance(radius_tok, Token)
        return AroundLineFilter(
            radius=float(radius_tok),
            points=list(children[1:]),
            token=radius_tok,
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
        raise UnsupportedFeatureError(
            "changed filter is not supported", children[0]
        )

    def user_filter(self, children: list[Any]) -> UserFilter:
        assert isinstance(children[0], Token)
        return UserFilter(
            users=[_unquote(t) for t in children], token=children[0]
        )

    def uid_filter(self, children: list[Any]) -> UidFilter:
        assert isinstance(children[0], Token)
        return UidFilter(
            uids=[int(t) for t in children], token=children[0]
        )

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
            ref.required_types = _AREAS
            return AreaSetFilter(set_ref=ref, token=ref.token)
        return AreaSetFilter(
            set_ref=SetReference(name="._", token=None, required_types=_AREAS),
            token=None,
        )

    def area_id_filter(self, children: list[Any]) -> AreaIdFilter:
        assert isinstance(children[0], Token)
        return AreaIdFilter(area_id=int(children[0]), token=children[0])

    def recurse_filter(self, children: list[Any]) -> RecurseFilter:
        type_tok = children[0]
        assert isinstance(type_tok, Token)
        recurse_type = RecurseFilterType(str(type_tok))
        ref = SetReference(name="._", token=None)
        role: str | None = None
        for child in children[1:]:
            if isinstance(child, SetReference):
                ref = child
            elif isinstance(child, str):
                role = child
        match recurse_type:
            case RecurseFilterType.BN:
                ref.required_types = _NODES
                input_types: frozenset[ElementType] | None = _NODES
                # TODO: output_types depends on element type (way→_WAYS, rel→_RELATIONS)
                # fill in from query_stmt transformer once that exists
                output_types: frozenset[ElementType] | None = None
            case RecurseFilterType.BW:
                ref.required_types = _WAYS
                input_types = _WAYS
                output_types = _RELATIONS
            case RecurseFilterType.BR:
                ref.required_types = _RELATIONS
                input_types = _RELATIONS
                output_types = _RELATIONS
            case RecurseFilterType.W:
                ref.required_types = _WAYS
                input_types = _WAYS
                output_types = _NODES
            case RecurseFilterType.R:
                ref.required_types = _RELATIONS
                input_types = _RELATIONS
                # TODO: output_types depends on element type (node→_NODES, way→_WAYS,
                # rel→_RELATIONS); fill in from query_stmt transformer once that exists
                output_types = None
        return RecurseFilter(
            recurse_type=recurse_type,
            set_ref=ref,
            role=role,
            token=type_tok,
            input_types=input_types,
            output_types=output_types,
        )

    def way_count_filter(self, children: list[Any]) -> WayCountFilter:
        min_count, max_count, exact, token = children[0]
        return WayCountFilter(
            min_count=min_count, max_count=max_count, exact=exact, token=token,
            input_types=_WAYS, output_types=_NODES,
        )

    def way_link_filter(self, children: list[Any]) -> None:
        min_count, max_count, exact, token = children[0]
        raise UnsupportedFeatureError(
            "way_link filter is not supported", token
        )

    def set_filter(self, children: list[Any]) -> SetFilter:
        assert isinstance(children[0], Token)
        return SetFilter(
            set_ref=SetReference(name=str(children[0]), token=children[0]),
            token=children[0],
        )

    def pivot_filter(self, children: list[Any]) -> PivotFilter:
        if children:
            ref = children[0]
            assert isinstance(ref, SetReference)
            ref.required_types = _AREAS
            return PivotFilter(set_ref=ref, token=ref.token,
                input_types=_WR, output_types=_WR,
            )
        return PivotFilter(
            set_ref=SetReference(name="._", token=None, required_types=_AREAS),
            input_types=_WR, output_types=_WR,
            token=None,
        )

    def if_filter(self, children: list[Any]) -> IfFilter:
        evaluator = children[0]
        assert isinstance(evaluator, Evaluator)
        token = evaluator.token
        return IfFilter(evaluator=evaluator, token=token)

    # Evaluators

    def ternary_expr(self, children: list[Any]) -> TernaryExpression:
        condition = children[0]
        true_expression = children[1]
        false_expression = children[2]
        token = children[0].token
        return TernaryExpression(
            condition=condition, true_expression=true_expression,
            false_expression=false_expression, token=token,
            )

    def or_expr(self, children: list[Any]) -> BinaryExpression:
        operator = BinaryOperator.OR
        operands = children
        token = children[0].token
        return BinaryExpression(operator=operator, operands=operands, token=token)

    def and_expr(self, children: list[Any]) -> BinaryExpression:
        operator = BinaryOperator.AND
        operands = children
        token = children[0].token
        return BinaryExpression(operator=operator, operands=operands, token=token)

    def not_expr(self, children: list[Any]) -> UnaryExpression:
        operator = UnaryOperator.NOT
        operand = children[1]
        token = children[0]
        return UnaryExpression(operator=operator, operand=operand, token=token)

    def compare_expr(self, children: list[Any]) -> CompareExpression:
        left_operand = children[0]
        operator = CompareOperator(children[1].value)
        right_operand = children[2]
        token = children[0].token
        return CompareExpression(left_operand=left_operand, operator=operator, 
            right_operand=right_operand, token=token,
        )

    def add_expr(self, children: list[Any]) -> AddExpression:
        left_operand = children[0]
        operator = AddOperator(children[1].value)
        right_operand = children[2]
        token = children[0].token
        return AddExpression(
            left_operand=left_operand,
            operator=operator,
            right_operand=right_operand,
            token=token,
        )

    # mul_expr

    # unary_expr

    def literal_expr(self, children: list[Any]) -> LiteralExpression:
        token=children[0]
        assert isinstance(token, Token)
        value = _unquote(token)
        return LiteralExpression(value=value, token=token)

