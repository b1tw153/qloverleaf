from lark import Lark, Token, Tree
from lark.exceptions import UnexpectedInput, UnexpectedToken

from qloverleaf.exceptions import ParseError

parser = Lark.open("grammar.lark", rel_to=__file__, parser="earley", start="query")


def parse(query: str) -> Tree[Token]:
    try:
        return parser.parse(query)
    except UnexpectedToken as e:
        raise ParseError(str(e), e.token) from e
    except UnexpectedInput as e:
        raise ParseError(str(e)) from e
