import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from lark import Token, Transformer, Tree
from lark.exceptions import VisitError

from qloverleaf.exceptions import UnsupportedFeatureError


@dataclass
class SetRef:
    name: str           # canonical name; "._" if implicit
    token: Token | None # None if implicit
    versioned: str = "" # filled in by SSA phase


@dataclass
class Warning:
    message: str
    token: Token


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


@dataclass
class BboxFilter:
    south: float
    west: float
    north: float
    east: float
    token: Token


@dataclass
class RecurseFilter:
    recurse_type: RecurseFilterType
    set_ref: SetRef
    role: str | None
    token: Token


@dataclass
class AreaSetFilter:
    set_ref: SetRef
    token: Token | None  # None when set_ref is implicit


@dataclass
class AreaIdFilter:
    area_id: int
    token: Token


@dataclass
class UserFilter:
    users: list[str]
    token: Token


@dataclass
class UidFilter:
    uids: list[int]
    token: Token


@dataclass
class NewerFilter:
    timestamp: datetime
    token: Token


@dataclass
class PolygonFilter:
    points: list[tuple[float, float]]
    token: Token


@dataclass
class AroundSetFilter:
    radius: float
    set_ref: SetRef
    token: Token


@dataclass
class AroundPointFilter:
    radius: float
    lat: float
    lon: float
    token: Token


@dataclass
class AroundLineFilter:
    radius: float
    points: list[tuple[float, float]]
    token: Token


@dataclass
class IdFilter:
    ids: list[int]
    token: Token


@dataclass
class TagKeyFilter:
    key: str
    absent: bool
    token: Token


@dataclass
class TagValueFilter:
    key: str
    op: TagFilterOp
    value: str
    case_insensitive: bool
    token: Token


_ESCAPE_MAP = {'n': '\n', 't': '\t', '"': '"', "'": "'", '\\': '\\'}


def _parse_datetime(token: Token) -> datetime:
    v = str(token)
    if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
        v = v[1:-1]
    return datetime.fromisoformat(v)


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


class OverpassTransformer(Transformer[Token, Any]):
    def __init__(self) -> None:
        super().__init__()
        self.warnings: list[Warning] = []

    def transform(self, tree: Tree[Token]) -> Any:
        try:
            return super().transform(tree)
        except VisitError as e:
            raise e.orig_exc from e


    def set_ref(self, children: list[Any]) -> SetRef:
        assert isinstance(children[0], Token)
        return SetRef(name=str(children[0]), token=children[0])

    def around_radius(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

    def recurse_role(self, children: list[Any]) -> str:
        assert isinstance(children[0], Token)
        return _unquote(children[0])

    def recurse_filter(self, children: list[Any]) -> RecurseFilter:
        type_tok = children[0]
        assert isinstance(type_tok, Token)
        ref = SetRef(name="._", token=None)
        role: str | None = None
        for child in children[1:]:
            if isinstance(child, SetRef):
                ref = child
            elif isinstance(child, str):
                role = child
        return RecurseFilter(
            recurse_type=RecurseFilterType(str(type_tok)),
            set_ref=ref,
            role=role,
            token=type_tok,
        )

    def area_set_filter(self, children: list[Any]) -> AreaSetFilter:
        if children:
            ref = children[0]
            assert isinstance(ref, SetRef)
            return AreaSetFilter(set_ref=ref, token=ref.token)
        return AreaSetFilter(set_ref=SetRef(name="._", token=None), token=None)

    def area_id_filter(self, children: list[Any]) -> AreaIdFilter:
        assert isinstance(children[0], Token)
        return AreaIdFilter(area_id=int(children[0]), token=children[0])

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

    def newer_filter(self, children: list[Any]) -> NewerFilter:
        assert isinstance(children[0], Token)
        return NewerFilter(timestamp=_parse_datetime(children[0]), token=children[0])

    def changed_filter(self, children: list[Any]) -> None:
        assert isinstance(children[0], Token)
        raise UnsupportedFeatureError(
            "changed filter is not supported", children[0]
        )

    def poly_lat_lon(self, children: list[Any]) -> tuple[float, float, Token]:
        lat_tok, lon_tok = children
        assert isinstance(lat_tok, Token)
        assert isinstance(lon_tok, Token)
        return (float(lat_tok), float(lon_tok), lat_tok)

    def polygon_filter(self, children: list[Any]) -> PolygonFilter:
        first_token = children[0][2]
        assert isinstance(first_token, Token)
        return PolygonFilter(
            points=[(lat, lon) for lat, lon, _ in children],
            token=first_token,
        )

    def around_lat_lon(self, children: list[Any]) -> tuple[float, float]:
        lat_tok, lon_tok = children
        assert isinstance(lat_tok, Token)
        assert isinstance(lon_tok, Token)
        return (float(lat_tok), float(lon_tok))

    def around_set_filter(self, children: list[Any]) -> AroundSetFilter:
        if len(children) == 1:
            ref = SetRef(name="._", token=None)
            radius_tok = children[0]
        else:
            ref, radius_tok = children[0], children[1]
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

    def number(self, children: list[Any]) -> Token:
        assert isinstance(children[0], Token)
        return children[0]

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
