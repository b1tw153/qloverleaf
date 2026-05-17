from collections.abc import AsyncGenerator

from lark import Token, Tree

from qloverleaf.exceptions import QueryError, UnsupportedFeatureError
from qloverleaf.query import Bbox, OutputFormat, QueryContext

MEDIA_TYPES = {
    OutputFormat.XML: "application/osm3s+xml",
    OutputFormat.JSON: "application/json",
    OutputFormat.CSV: "text/csv",
    OutputFormat.CUSTOM: "text/plain",
    OutputFormat.POPUP: "application/html",
}


async def initialize(query: QueryContext) -> tuple[AsyncGenerator[str, None], str]:
    _apply_global_settings(query)
    # TODO: transform AST to IR
    # TODO: walk IR and annotate with versioned set names
    # TODO: walk IR and flag dead code (unused output)
    # TODO: walk IR and flag element type mismatches
    return _execute(query), MEDIA_TYPES[query.out]


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


def _apply_global_settings(query: QueryContext) -> None:
    # apply global timeout
    matches = list(query.tree.find_data("global_timeout"))
    if len(matches) > 1:
        token = matches[1].children[0]
        assert isinstance(token, Token)
        raise QueryError("Duplicate global timeout setting", token)

    if len(matches) == 1:
        global_timeout = matches[0]
        assert len(global_timeout.children) == 1, (
            f"Unexpected parsing error: Invalid global timeout {global_timeout}"
        )
        global_timeout_param = global_timeout.children[0]
        assert isinstance(global_timeout_param, Token), (
            f"Unexpected parsing error: Invalid global timeout {global_timeout}"
        )
        query.timeout = int(global_timeout_param.value)
        print(f"[timeout:{int(global_timeout_param.value)}]")

    # apply global maxsize
    matches = list(query.tree.find_data("global_maxsize"))
    if len(matches) > 1:
        token = matches[1].children[0]
        assert isinstance(token, Token)
        raise QueryError("Duplicate global maxsize setting", token)

    if len(matches) == 1:
        global_maxsize = matches[0]
        assert len(global_maxsize.children) == 1, (
            f"Unexpected parsing error: Invalid global maxsize {global_maxsize}"
        )
        global_maxsize_param = global_maxsize.children[0]
        assert isinstance(global_maxsize_param, Token), (
            f"Unexpected parsing error: Invalid global maxsize {global_maxsize}"
        )
        query.maxsize = int(global_maxsize_param.value)
        print(f"[maxsize:{int(global_maxsize_param.value)}]")

    # apply global output
    matches = list(query.tree.find_data("global_output"))
    if len(matches) > 1:
        raise QueryError("Duplicate global output setting")

    if len(matches) == 1:
        # walk down to the global_output_* node and get its Token
        global_output_node = matches[0]
        assert len(global_output_node.children) == 1, (
            "Unexpected parsing error: Malformed global output node"
        )
        global_output_setting = global_output_node.children[0]
        assert isinstance(global_output_setting, Tree), (
            "Unexpected parsing error: Malformed global output node"
        )
        global_output_token = global_output_setting.data
        assert isinstance(global_output_token, Token), (
            "Unexpected parsing error: Malformed global output token"
        )

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
                assert False, (
                    f"Unexpected global output type: {global_output_token.value}"
                )

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

    # apply global bbox
    matches = list(query.tree.find_data("global_bbox"))
    if len(matches) > 1:
        token = matches[1].children[0]
        assert isinstance(token, Token)
        raise QueryError("Duplicate global bbox setting", token)
    if len(matches) == 1:
        s_tok, w_tok, n_tok, e_tok = matches[0].children
        assert isinstance(s_tok, Token)
        assert isinstance(w_tok, Token)
        assert isinstance(n_tok, Token)
        assert isinstance(e_tok, Token)
        south, west, north, east = (s_tok.value, w_tok.value, n_tok.value, e_tok.value)
        if float(south) >= float(north):
            raise QueryError("Invalid global bbox parameters", s_tok)
        query.bbox = Bbox(south, west, north, east)
        print(f"[bbox:{query.bbox}]")

    # apply global date
    matches = list(query.tree.find_data("global_date"))
    if len(matches) >= 1:
        token = matches[0].children[0]
        assert isinstance(token, Token)
        raise UnsupportedFeatureError("Global date setting is not supported", token)

    # apply global diff
    matches = list(query.tree.find_data("global_diff"))
    if len(matches) >= 1:
        token = matches[0].children[0]
        assert isinstance(token, Token)
        raise UnsupportedFeatureError("Global diff setting is not supported", token)

    # apply global adiff
    matches = list(query.tree.find_data("global_adiff"))
    if len(matches) >= 1:
        token = matches[0].children[0]
        assert isinstance(token, Token)
        raise UnsupportedFeatureError("Global adiff setting is not supported", token)


async def _execute(query: QueryContext) -> AsyncGenerator[str, None]:
    yield query.tree.pretty()
    yield _dump_ast(query.tree)
    # yield _dump_ir(query.ir)
