from lark import Lark, Token, Tree

parser = Lark.open("grammar.lark", rel_to=__file__, parser="earley", start="query")

def parse(query: str) -> Tree[Token]:
    return parser.parse(query)
