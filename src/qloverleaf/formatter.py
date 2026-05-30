import json
from typing import Any

import httpx
from lark import Token, Tree

from qloverleaf.collator import collate_count, collate_elements
from qloverleaf.exceptions import (
    QueryWarning,
    UnimplementedFeatureError,
    UnsupportedFeatureError,
)
from qloverleaf.executor import QLEVER_ENDPOINT
from qloverleaf.query_context import OutputFormat, QueryContext
from qloverleaf.transformer import OutStatement
from qloverleaf.translator import _dump_sparql_pattern
from qloverleaf.types import SetStateEntry, SparqlPattern

_META_FIELDS = ("version", "timestamp", "changeset", "uid", "user")

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
            pass
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
            return _format_begin_xml()
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


def _format_begin_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<osm version="0.6" generator="{_GENERATOR}">\n'
        f"<note>{_COPYRIGHT}</note>\n"
        "<meta/>\n\n"
    )


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


def format_warnings(warnings: list[QueryWarning]) -> str:
    global _output_format
    output = ""
    for warning in warnings:
        match _output_format:
            case OutputFormat.XML:
                _remarks.append(str(warning))
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
            _remarks.append(str(error))
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


def format_debug(
    set_state_entry: SetStateEntry, pattern: SparqlPattern, query: str
) -> str:
    global _output_format
    match _output_format:
        case OutputFormat.XML:
            content = _format_debug_raw(set_state_entry, pattern, query)
            safe = content.replace("]]>", "]]]]><![CDATA[>")
            return f"<debug><![CDATA[\n{safe}]]></debug>\n"
        case OutputFormat.JSON:
            # TODO: return JSON dump of SetStateEntry
            return ""
        case OutputFormat.CSV:
            # TODO: return CSV dump of SetStateEntry
            return ""
        case OutputFormat.RAW:
            return _format_debug_raw(set_state_entry, pattern, query)
        case _:
            assert False


def _format_debug_raw(
    set_state_entry: SetStateEntry, pattern: SparqlPattern, query: str
) -> str:
    lines: list[str] = []

    if set_state_entry.pattern:
        lines.append("input_pattern:")
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

    lines.append("output_pattern:")
    for line in _dump_sparql_pattern(pattern).splitlines():
        lines.append(f"  {line}")

    lines.append("query:")
    for line in query.splitlines():
        lines.append(f"  {line}")

    return "\n".join(lines) + "\n"


def format_output(data: dict[str, Any], stmt: OutStatement) -> str:
    global _output_format
    match _output_format:
        case OutputFormat.XML:
            if stmt.count:
                elements = [collate_count(data)]
            else:
                elements = collate_elements(data, stmt)
            return "".join(_element_to_xml(elem) for elem in elements)
        case OutputFormat.JSON:
            if stmt.count:
                elements = [collate_count(data)]
            else:
                elements = collate_elements(data, stmt)
            output = ""
            for element in elements:
                global _first_element
                if _first_element:
                    _first_element = False
                else:
                    output += ","
                output += f"\n{json.dumps(element, indent=2)}\n"
            return output
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
            return _format_end_xml()
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
    return f"\n  ]{remark}}}\n"


def _format_end_xml() -> str:
    remarks = "".join(f"\n<remark> {_xml_escape(r)} </remark>" for r in _remarks)
    return f"{remarks}\n\n</osm>\n"


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xml_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _fmt_coord(v: float) -> str:
    return f"{v:.7f}"


def _element_to_xml(elem: dict[str, Any]) -> str:
    elem_type = elem["type"]
    elem_id = elem["id"]

    attrs = f' id="{elem_id}"'
    if "lat" in elem:
        attrs += f' lat="{_fmt_coord(elem["lat"])}" lon="{_fmt_coord(elem["lon"])}"'
    for field in _META_FIELDS:
        if field in elem:
            val = elem[field]
            attrs += f' {field}="{val if not isinstance(val, str) else _xml_attr(val)}"'

    children = ""

    if "bounds" in elem:
        b = elem["bounds"]
        children += (
            f'  <bounds minlat="{_fmt_coord(b["minlat"])}"'
            f' minlon="{_fmt_coord(b["minlon"])}"'
            f' maxlat="{_fmt_coord(b["maxlat"])}"'
            f' maxlon="{_fmt_coord(b["maxlon"])}"/>\n'
        )

    if "center" in elem:
        c = elem["center"]
        children += (
            f'  <center lat="{_fmt_coord(c["lat"])}" lon="{_fmt_coord(c["lon"])}"/>\n'
        )

    if elem_type == "way" and "nodes" in elem:
        geometry = elem.get("geometry", [])
        for i, ref in enumerate(elem["nodes"]):
            if i < len(geometry):
                g = geometry[i]
                children += (
                    f'  <nd ref="{ref}"'
                    f' lat="{_fmt_coord(g["lat"])}"'
                    f' lon="{_fmt_coord(g["lon"])}"/>\n'
                )
            else:
                children += f'  <nd ref="{ref}"/>\n'

    if elem_type == "relation" and "members" in elem:
        for member in elem["members"]:
            mtype = member["type"]
            mref = member["ref"]
            mrole = _xml_attr(member["role"])
            mattrs = f' type="{mtype}" ref="{mref}" role="{mrole}"'
            if "lat" in member:
                mattrs += (
                    f' lat="{_fmt_coord(member["lat"])}"'
                    f' lon="{_fmt_coord(member["lon"])}"'
                )
            member_children = ""
            if "geometry" in member:
                for g in member["geometry"]:
                    member_children += (
                        f'    <nd lat="{_fmt_coord(g["lat"])}"'
                        f' lon="{_fmt_coord(g["lon"])}"/>\n'
                    )
            if member_children:
                children += f"  <member{mattrs}>\n{member_children}  </member>\n"
            else:
                children += f"  <member{mattrs}/>\n"

    if "tags" in elem:
        for k, v in elem["tags"].items():
            children += f'  <tag k="{_xml_attr(k)}" v="{_xml_attr(v)}"/>\n'

    if not children:
        return f"<{elem_type}{attrs}/>\n"
    return f"<{elem_type}{attrs}>\n{children}</{elem_type}>\n"
