from collections.abc import AsyncGenerator

from lark import Token, Tree

from qloverleaf.query import OutputFormat, Query

MEDIA_TYPES = {
    OutputFormat.XML: "application/osm3s+xml",
    OutputFormat.JSON: "application/json",
    OutputFormat.CSV: "text/csv",
    OutputFormat.CUSTOM: "text/plain",
    OutputFormat.POPUP: "application/html",
}


async def initialize(query: Query) -> tuple[str, AsyncGenerator[str, None]]:
    _apply_global_settings(query)
    return MEDIA_TYPES[query.out], _execute(query)


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


def _apply_global_settings(query: Query) -> None:
    # apply global timeout
    matches = list(query.tree.find_data("global_timeout"))
    if len(matches) > 1:
        # TODO: Make this a QueryError
        raise Exception("Duplicate global timeout setting")

    if len(matches) == 1:
        global_timeout = matches[0]
        assert len(global_timeout.children) == 1, \
            f"Unexpected parsing error: Invalid global timeout {global_timeout}"
        global_timeout_param = global_timeout.children[0]
        assert isinstance(global_timeout_param, Token), \
            f"Unexpected parsing error: Invalid global timeout {global_timeout}"
        query.timeout = int(global_timeout_param.value)
        print(f"[timeout:{int(global_timeout_param.value)}]")

    # apply global maxsize
    matches = list(query.tree.find_data("global_maxsize"))
    if len(matches) > 1:
        # TODO: Make this a QueryError
        raise Exception("Duplicate global maxsize setting")

    if len(matches) == 1:
        global_maxsize = matches[0]
        assert len(global_maxsize.children) == 1, \
            f"Unexpected parsing error: Invalid global maxsize {global_maxsize}"
        global_maxsize_param = global_maxsize.children[0]
        assert isinstance(global_maxsize_param, Token), \
            f"Unexpected parsing error: Invalid global maxsize {global_maxsize}"
        query.maxsize = int(global_maxsize_param.value)
        print(f"[maxsize:{int(global_maxsize_param.value)}]")

    # apply global date
    matches = list(query.tree.find_data("global_date"))
    if len(matches) >= 1:
        # TODO: Make this a QueryError
        raise Exception("Unsupported global date setting")

    # apply global diff
    matches = list(query.tree.find_data("global_diff"))
    if len(matches) >= 1:
        # TODO: Make this a QueryError
        raise Exception("Unsupported global diff setting")

    # apply global adiff
    matches = list(query.tree.find_data("global_adiff"))
    if len(matches) >= 1:
        # TODO: Make this a QueryError
        raise Exception("Unsupported global adiff setting")

    # apply global output
    matches = list(query.tree.find_data("global_output"))
    if len(matches) > 1:
        # TODO: Make this a QueryError
        raise Exception("Duplicate global output setting")

    if len(matches) == 1:
        # walk down to the global_output_* node and get its Token
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
                query.out = OutputFormat.XML
            case "global_output_json":
                query.out = OutputFormat.JSON
            case "global_output_csv":
                query.out = OutputFormat.CSV
            case "global_output_custom":
                query.out = OutputFormat.CUSTOM
            case "global_output_popup":
                query.out = OutputFormat.POPUP
            case _:
                assert False, \
                    f"Unexpected global output type: {global_output_token.value}"
        
        # collect parameter subtree
        assert len(global_output_setting.children) <= 1, (
            "Unexpected parsing error: "
            f"Invalid global output parameters {global_output_setting}"
        )
        if len(global_output_setting.children) == 1:
            out_params = global_output_setting.children[0]
            if isinstance(out_params, Tree):
                query.out_params = out_params
        print(f"[out:{query.out}({query.out_params})]")


async def _execute(query: Query) -> AsyncGenerator[str, None]:
    yield query.tree.pretty()
    yield _dump(query.tree)
    # walk the top level and collect settings/statements
    for child in query.tree.children:
        assert isinstance(child, Tree), \
            f"Unexpected paring error: Invalid top level element: {child}"
        data = child.data
        assert isinstance(data, Token), \
            f"Unexpected paring error: Invalid top level element: {child}"
        match data.value:
            case "global_setting":
                print(child)
            case "statement":
                print(child)
            case _:
                assert False, \
                    f"Unexpected parsing error: Unknown top level element {child}"

