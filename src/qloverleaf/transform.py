import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from lark import Token, Transformer

from qloverleaf.exceptions import UnsupportedFeatureError


class TagFilterOp(Enum):
    EQ = "="
    NEQ = "!="
    REGEX = "~"
    NOT_REGEX = "!~"


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
