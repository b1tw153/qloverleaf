from lark import Lark, Tree

parser = Lark.open("grammar.lark", rel_to=__file__, parser="earley", start="query")

def parse(query: str) -> Tree:
    return parser.parse(query)
