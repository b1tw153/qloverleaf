from collections.abc import AsyncGenerator
from dataclasses import replace

import httpx
from lark import Token, Tree

from qloverleaf.composer import compose
from qloverleaf.exceptions import QueryError, UnsupportedFeatureError
from qloverleaf.executor import parse_results, query_qlever
from qloverleaf.formatter import (
    format_begin,
    format_debug,
    format_end,
    format_error,
    format_init,
    format_output,
    format_warnings,
)
from qloverleaf.query_context import Bbox, OutputFormat, QueryContext
from qloverleaf.transformer import (
    _AREA,
    _NWR,
    ElementType,
    OutStatement,
    OverpassTransformer,
)
from qloverleaf.translator import (
    render_query,
    translate,
)
from qloverleaf.types import SetState, SetStateEntry, SparqlPattern

MEDIA_TYPES = {
    OutputFormat.XML: "application/osm3s+xml",
    OutputFormat.JSON: "application/json",
    OutputFormat.CSV: "text/csv",
    OutputFormat.CUSTOM: "text/plain",
    OutputFormat.POPUP: "application/html",
    OutputFormat.RAW: "application/json",
}


async def initialize(query: QueryContext) -> tuple[AsyncGenerator[str, None], str]:
    _apply_global_settings(query)
    # TODO: (deferred) refactor global settings parsing to use the transformer
    # and apply the settings from the ir instead of directly from the parse tree

    query.ir = OverpassTransformer().transform(query.tree)

    await format_init(query)

    return _execute(query), MEDIA_TYPES[query.out]


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
        # print(f"[timeout:{int(global_timeout_param.value)}]")

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
        # print(f"[maxsize:{int(global_maxsize_param.value)}]")

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
            case "global_output_raw":
                query.out = OutputFormat.RAW
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
        # print(f"[out:{query.out}({query.out_params})]")

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
        # print(f"[bbox:{query.bbox}]")

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
    assert query.ir is not None

    set_state: SetState = {}
    execution_queue: list[SparqlPattern] = []

    try:
        yield format_begin()

        yield format_warnings(query.ir.warnings)

        # Translate all statements and build initial execution queue
        for statement in query.ir.statements:
            patterns = translate(statement)
            execution_queue.extend(patterns)

        # Process execution queue
        async with httpx.AsyncClient() as client:
            while execution_queue:
                pattern = execution_queue.pop(0)

                # Create set state entry if pattern produces a set
                if pattern.result_set_name:
                    if pattern.result_set_name not in set_state:
                        set_state[pattern.result_set_name] = SetStateEntry(
                            pattern=pattern,
                            nwr_results=None,
                            area_results=None,
                        )

                # Try to compose the pattern
                composed = compose(pattern, set_state)

                # Case 1: Fully composed (cold pattern, no dependencies)
                if composed is not None and not composed.injections:
                    if pattern.result_set_name:
                        # Normal pattern - store and continue without execution
                        set_state[pattern.result_set_name].pattern = composed
                        continue
                    else:
                        # OutStatement - must execute even if fully composed
                        working_pattern = composed
                        # Fall through to execution

                # Case 2 & 3: Has dependencies or not composable
                # Determine which pattern to work with
                working_pattern = composed if composed is not None else pattern

                # If pattern has injections, materialize dependencies first
                if working_pattern.injections:
                    # Collect dependency patterns that need materialization
                    dependencies_to_materialize = []
                    for injection in working_pattern.injections:
                        dependency_entry = set_state.get(injection.set_name)
                        # Only queue if not already materialized
                        if (
                            dependency_entry
                            and not dependency_entry.nwr_results
                            and not dependency_entry.area_results
                        ):
                            if dependency_entry.pattern:
                                dependencies_to_materialize.append(
                                    dependency_entry.pattern
                                )

                    # If we have unmaterialized dependencies, queue them first
                    if dependencies_to_materialize:
                        # Force dependencies to execute by marking them hot
                        hot_dependencies = [
                            replace(dep_pattern, materialize=True)
                            for dep_pattern in dependencies_to_materialize
                        ]
                        # Push hot dependencies to front of queue
                        execution_queue = hot_dependencies + execution_queue
                        # Re-queue current pattern to retry after deps are materialized
                        execution_queue.insert(len(hot_dependencies), pattern)
                        continue

                # Execute the pattern (all dependencies are materialized,
                # or pattern is hot)
                sparql = render_query(working_pattern, set_state)
                data = await query_qlever(sparql, client)

                # Store results if pattern produces a set; otherwise just yield
                if pattern.result_set_name:
                    assert pattern.output_set is not None
                    assert pattern.output_set.content_types is not None
                    assert not (
                        pattern.output_set.content_types & _NWR
                        and pattern.output_set.content_types & _AREA
                    )  # mixed set content is not yet supported
                    results = parse_results(data, pattern.result_set_name)
                    if ElementType.AREA in pattern.output_set.content_types:
                        set_state[pattern.result_set_name].area_results = results
                    else:
                        set_state[pattern.result_set_name].nwr_results = results

                if isinstance(pattern.statements[-1], OutStatement):
                    stmt = pattern.statements[-1]
                    if stmt.debug:
                        yield format_debug(
                            set_state[stmt.input_set.identifier], pattern
                        )
                    else:
                        yield format_output(data, stmt)

    except Exception as e:
        yield format_error(e)
    finally:
        yield format_end()
