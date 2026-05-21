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


def _dump_ast(node: Tree[Token] | Token, indent: int = 0) -> str:
    prefix = "  " * indent
    if isinstance(node, Token):
        return (
            f"{prefix}Token("
            f"type={node.type!r}, "
            f"value={node.value!r}, "
            f"line={node.line}, "
            f"column={node.column}, "
            f"end_line={node.end_line}, "
            f"end_column={node.end_column})\n"
        )
    data = node.data
    if isinstance(data, Token):
        lines = (
            f"{prefix}Token("
            f"type={data.type!r}, "
            f"value={data.value!r}, "
            f"line={data.line}, "
            f"column={data.column}, "
            f"end_line={data.end_line}, "
            f"end_column={data.end_column})\n"
        )
    else:
        lines = f"{prefix}Alias({node.data!r})\n"
    for child in node.children:
        lines += _dump_ast(child, indent + 1)
    return lines
