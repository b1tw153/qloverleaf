from collections.abc import AsyncGenerator

from lark import Token, Tree

from qloverleaf.query import Query

MEDIA_TYPE_XML = "application/osm3s+xml"
MEDIA_TYPE_JSON = "application/json"
MEDIA_TYPE_CSV = "text/csv"
MEDIA_TYPE_CUSTOM = "text/plain"
MEDIA_TYPE_POPUP = "application/html"


async def initialize(query: Query) -> tuple[str, AsyncGenerator[str, None]]:
    media_type = get_media_type(query.tree)
    return media_type, _execute(query)

def get_media_type(tree: Tree[Token]) -> str:
    media_type = MEDIA_TYPE_XML

    matches = list(tree.find_data("global_output"))
    if not matches:
        # TODO: Return the real result when we have formatted output
        print(media_type)
        return "text/plain"
    if len(matches) > 1:
        # TODO: Make this a QueryError
        raise Exception("Duplicate global output setting")

    global_output_node = matches[0]
    assert len(global_output_node.children) == 1, \
        "Unexpected parsing error: Malformed global output node"

    global_output_setting = global_output_node.children[0]
    assert isinstance(global_output_setting, Tree), \
        "Unexpected parsing error: Malformed global output node"
    global_output_token = global_output_setting.data
    assert isinstance(global_output_token, Token), \
        "Unexpected parsing error: Malformed global output token"

    match global_output_token.value:
        case "global_output_xml":
            media_type = MEDIA_TYPE_XML
        case "global_output_json":
            media_type = MEDIA_TYPE_JSON
        case "global_output_csv":
            media_type = MEDIA_TYPE_CSV
        case "global_output_custom":
            media_type = MEDIA_TYPE_CUSTOM
        case "global_output_popup":
            media_type = MEDIA_TYPE_POPUP
        case _:
            assert False, f"Unexpected global output type: {global_output_token.value}"

    # TODO: Return the real result when we have formatted output
    print(media_type)
    return "text/plain"


def _dump(node: Tree[Token] | Token, indent: int = 0) -> str:
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
        lines += _dump(child, indent + 1)
    return lines


async def _execute(query: Query) -> AsyncGenerator[str, None]:
    yield query.tree.pretty()
    yield _dump(query.tree)
