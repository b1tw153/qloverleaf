import pytest
from lark import Token, Tree

from qloverleaf.exceptions import ParseError
from qloverleaf.parser import parse


# ---------------------------------------------------------------------------
# Valid queries — just confirm they parse without error
# ---------------------------------------------------------------------------

VALID_QUERIES = [
    # Minimal
    "out;",
    "node;out;",
    # Global settings
    "[out:json];node[natural=peak];out ids;",
    "[timeout:25];node[natural=peak];out ids;",
    "[out:json][timeout:25];node[natural=peak];out ids;",
    # Tag filters
    "node[natural=peak];out ids;",
    "node[natural];out ids;",
    "node[!natural];out ids;",
    "node[natural!=peak];out ids;",
    'node[natural~"peak|volcano"];out ids;',
    'node[natural~"peak",i];out ids;',
    # Bbox filter
    "node[natural=peak](51.5,-0.2,51.6,-0.1);out ids;",
    # ID filters
    "node(1);out ids;",
    "node(id:1,2,3);out ids;",
    # Named sets
    "node[natural=peak]->.peaks;.peaks out ids;",
    "node[natural=peak]->.a;node[geological=meteor_crater]->.b;(.a;.b;);out ids;",
    # Union
    "(node[natural=peak];way[natural=peak];);out ids;",
    # Multiple tag filters (AND)
    "node[natural=stone][geological=glacial_erratic];out ids;",
    # out options
    "node[natural=peak];out tags;",
    "node[natural=peak];out body;",
    "node[natural=peak];out meta;",
    "node[natural=peak];out count;",
    "node[natural=peak];out geom;",
    # Recursion
    "way[highway=primary];>;out ids;",
    "node[natural=peak];<;out ids;",
    # Item statement
    "node[natural=peak]->.a;.a;out ids;",
]


@pytest.mark.parametrize("query", VALID_QUERIES)
def test_parse_valid(query: str) -> None:
    tree = parse(query)
    assert isinstance(tree, Tree)
    assert tree.data == "query"


# ---------------------------------------------------------------------------
# Invalid queries — confirm they raise a parse error
# ---------------------------------------------------------------------------

INVALID_QUERIES = [
    "node[;out ids;",          # unclosed tag filter
    "node[natural=peak]",      # missing semicolon
    "[out:xml;",               # unclosed global setting
    "gibberish",               # not a valid statement
    "node(1,2);out ids;",      # invalid ID filter syntax
]


@pytest.mark.parametrize("query", INVALID_QUERIES)
def test_parse_invalid(query: str) -> None:
    with pytest.raises(ParseError):
        parse(query)


# ---------------------------------------------------------------------------
# Tree structure — verify specific parse tree shapes
# ---------------------------------------------------------------------------

def _children_data(tree: Tree[Token]) -> list[str]:
    return [
        c.data if isinstance(c, Tree) else str(c)
        for c in tree.children
    ]


def test_tree_single_tag_filter() -> None:
    tree = parse("node[natural=peak];out ids;")
    assert _children_data(tree) == ["statement", "statement"]

    query_stmt = tree.children[0].children[0]
    assert isinstance(query_stmt, Tree)
    assert query_stmt.data == "query_stmt"
    assert query_stmt.children[0].data == "element_type_node"  # type: ignore[union-attr]
    assert query_stmt.children[1].data == "tag_filter_eq"      # type: ignore[union-attr]


def test_tree_global_settings() -> None:
    tree = parse("[out:json][timeout:25];node[natural=peak];out ids;")
    top = _children_data(tree)
    assert top[0] == "global_setting"
    assert top[1] == "global_setting"
    assert top[2] == "statement"
    assert top[3] == "statement"


def test_tree_named_set_assignment() -> None:
    tree = parse("node[natural=peak]->.peaks;out ids;")
    query_stmt = tree.children[0].children[0]
    assert isinstance(query_stmt, Tree)
    # Last child should be the set_assignment
    last = query_stmt.children[-1]
    assert isinstance(last, Tree)
    assert last.data == "set_assignment"


def test_tree_union() -> None:
    tree = parse("(node[natural=peak];way[natural=peak];);out ids;")
    union_stmt = tree.children[0].children[0]
    assert isinstance(union_stmt, Tree)
    assert union_stmt.data == "union_stmt"


def test_tree_multiple_tag_filters() -> None:
    tree = parse("node[natural=stone][geological=glacial_erratic];out ids;")
    query_stmt = tree.children[0].children[0]
    assert isinstance(query_stmt, Tree)
    filters = [c for c in query_stmt.children if isinstance(c, Tree) and "filter" in c.data]
    assert len(filters) == 2
