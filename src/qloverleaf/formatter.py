from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
from lark import Token, Tree

from qloverleaf.exceptions import UnimplementedFeatureError, UnsupportedFeatureError
from qloverleaf.executor import QLEVER_ENDPOINT
from qloverleaf.query_context import OutputFormat, QueryContext
from qloverleaf.transformer import Warning
from qloverleaf.translator import _dump_sparql_pattern

# TODO: consider refactoring to avoid circular imports
if TYPE_CHECKING:
    from qloverleaf.interpreter import SetStateEntry

_query_context: QueryContext
_output_format: OutputFormat
_output_params: Tree[Token] | None
_first_element: bool
_qlever_stats: dict[str, Any]
_remarks: list[str]

_VERSION = "0.1"
_COPYRIGHT = (
    "The data included in this document is from www.openstreetmap.org. "
    "The data is made available under ODbL."
)
_GENERATOR = f"Qloverleaf {_VERSION}"


async def format_init(context: QueryContext) -> None:
    global _query_context
    global _output_format
    global _output_params
    _query_context = context
    _output_format = context.out
    _output_params = context.out_params

    global _first_element
    _first_element = True

    global _remarks
    _remarks = []

    match _output_format:
        case OutputFormat.XML:
            raise UnimplementedFeatureError("XML output is not implemented", None)
        case OutputFormat.JSON:
            global _qlever_stats
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{QLEVER_ENDPOINT}?cmd=stats")
                response.raise_for_status()
                _qlever_stats = response.json()
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
            return _format_begin_json()
        case OutputFormat.CSV:
            # TODO: return CSV document header
            return ""
        case OutputFormat.RAW:
            # No document header
            return "\n"
        case _:
            assert False


def _format_begin_json() -> str:
    # use static header to leave elements open
    return (
        "{\n"
        f'  "version": {_VERSION},\n'
        f'  "generator": "{_GENERATOR}",\n'
        '  "osm3s": {\n'
        f'    "qlever_source": "{_qlever_stats["name-index"]}",\n'
        f'    "copyright": "{_COPYRIGHT}"\n'
        "  },\n"
        '  "elements": [\n'
    )


def format_warnings(warnings: list[Warning]) -> str:
    global _output_format
    output = ""
    for warning in warnings:
        match _output_format:
            case OutputFormat.XML:
                # TODO: return XML warnings
                pass
            case OutputFormat.JSON:
                _remarks.append(str(warning))
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
            # TODO: return XML errors
            return ""
        case OutputFormat.JSON:
            _remarks.append(str(error))
            return ""
        case OutputFormat.CSV:
            # TODO: return CSV errors
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
            return _format_end_json()
        case OutputFormat.CSV:
            # TODO: return CSV document footer
            return ""
        case OutputFormat.RAW:
            # No document footer
            return ""
        case _:
            assert False


def _format_end_json() -> str:
    # TODO: research how Overpass formats remark text
    remark = (
        f',\n  "remark": {json.dumps(". \n".join(_remarks))}\n' if _remarks else "\n"
    )
    return f"  ]{remark}}}\n"


# TODO: Format QLever JSON into Overpass XML and Overpass JSON
