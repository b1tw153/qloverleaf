import json
from typing import Any

from lark import Token, Tree

from qloverleaf.exceptions import UnimplementedFeatureError, UnsupportedFeatureError
from qloverleaf.interpreter import SetStateEntry
from qloverleaf.query_context import OutputFormat, QueryContext
from qloverleaf.transformer import Warning
from qloverleaf.translator import _dump_sparql_pattern

_query_context: QueryContext
_output_format: OutputFormat
_output_params: Tree[Token] | None


def format_init(context: QueryContext) -> None:
    global _query_context
    global _output_format
    global _output_params
    _query_context = context
    _output_format = context.out
    _output_params = context.out_params

    match _output_format:
        case OutputFormat.XML:
            raise UnimplementedFeatureError("XML output is not implemented", None)
        case OutputFormat.JSON:
            raise UnimplementedFeatureError("JSON output is not implemented", None)
        case OutputFormat.CSV:
            raise UnimplementedFeatureError("CSV output is not implemented", None)
        case OutputFormat.RAW:
            pass
        case _:
            raise UnsupportedFeatureError(
                f"Output type {_output_format.value} is not supported", None
            )


def format_begin() -> str:
    global _output_format
    match _output_format:
        case OutputFormat.XML:
            # TODO: return XML document header
            return ""
        case OutputFormat.JSON:
            # TODO: return JSON document header
            return ""
        case OutputFormat.CSV:
            # TODO: return CSV document header
            return ""
        case OutputFormat.RAW:
            # No document header
            return ""
        case _:
            assert False


def format_warnings(warnings: list[Warning]) -> str:
    global _output_format
    output = ""
    for warning in warnings:
        match _output_format:
            case OutputFormat.XML:
                # TODO: return XML warnings
                pass
            case OutputFormat.JSON:
                # TODO: return JSON warnings
                pass
            case OutputFormat.CSV:
                # TODO: return CSV warnings
                pass
            case OutputFormat.RAW:
                output += f"{str(warning)}\n"
            case _:
                assert False
    return output


def format_error(error: Exception) -> str:
    global _output_format
    match _output_format:
        case OutputFormat.XML:
            # TODO: return XML warnings
            return ""
        case OutputFormat.JSON:
            # TODO: return JSON warnings
            return ""
        case OutputFormat.CSV:
            # TODO: return CSV warnings
            return ""
        case OutputFormat.RAW:
            return f"{str(error)}\n"
        case _:
            return ""


def format_debug(set_state_entry: SetStateEntry) -> str:
    global _output_format
    match _output_format:
        case OutputFormat.XML:
            # TODO: return XML dump of SetStateEntry
            return ""
        case OutputFormat.JSON:
            # TODO: return JSON dump of SetStateEntry
            return ""
        case OutputFormat.CSV:
            # TODO: return CSV dump of SetStateEntry
            return ""
        case OutputFormat.RAW:
            return _format_debug_raw(set_state_entry)
        case _:
            assert False


def _format_debug_raw(set_state_entry: SetStateEntry) -> str:
    lines: list[str] = []

    if set_state_entry.pattern:
        lines.append("pattern:")
        for line in _dump_sparql_pattern(set_state_entry.pattern).splitlines():
            lines.append(f"  {line}")
    else:
        lines.append("pattern: None")

    if set_state_entry.nwr_results is not None:
        lines.append(f"nwr_results: {len(set_state_entry.nwr_results)} elements")
        for elem_type, uri in set_state_entry.nwr_results:
            lines.append(f"  {elem_type.value}: {uri}")
    else:
        lines.append("nwr_results: None")

    if set_state_entry.area_results is not None:
        lines.append(f"area_results: {len(set_state_entry.area_results)} elements")
        for elem_type, uri in set_state_entry.area_results:
            lines.append(f"  {elem_type.value}: {uri}")
    else:
        lines.append("area_results: None")

    return "\n".join(lines) + "\n"


def format_output(data: dict[str, Any]) -> str:
    global _output_format
    match _output_format:
        case OutputFormat.XML:
            # TODO: return Overpass/XML output
            return ""
        case OutputFormat.JSON:
            # TODO: return Overpass/GeoJSON output
            return ""
        case OutputFormat.CSV:
            # TODO: return CSV output
            return ""
        case OutputFormat.RAW:
            return json.dumps(data, indent=2)
        case _:
            assert False


def format_end() -> str:
    global _output_format
    match _output_format:
        case OutputFormat.XML:
            # TODO: return XML document footer
            return ""
        case OutputFormat.JSON:
            # TODO: return JSON document footer
            return ""
        case OutputFormat.CSV:
            # TODO: return CSV document footer
            return ""
        case OutputFormat.RAW:
            # No document footer
            return ""
        case _:
            assert False


# TODO: Format QLever JSON into Overpass XML and Overpass JSON
