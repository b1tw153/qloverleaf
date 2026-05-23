import pytest

from qloverleaf.exceptions import UnimplementedFeatureError
from qloverleaf.parser import parse
from qloverleaf.transform import OverpassTransformer
from qloverleaf.translator import SparqlPattern, ValuesInjection, translate


def _translate(text: str) -> list[SparqlPattern]:
    query = OverpassTransformer().transform(parse(text))
    return translate(query.statements[0])


# ---------------------------------------------------------------------------
# _translate_query — no filters
# ---------------------------------------------------------------------------


def test_translate_query_node_no_filters() -> None:
    pattern = _translate("node;")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_1 rdf:type osm:node ."]
    assert pattern.injections == []


def test_translate_query_way_no_filters() -> None:
    pattern = _translate("way;")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_1 rdf:type osm:way ."]
    assert pattern.injections == []


def test_translate_query_relation_no_filters() -> None:
    pattern = _translate("relation;")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_1 rdf:type osm:relation ."]
    assert pattern.injections == []


def test_translate_query_nwr_no_filters() -> None:
    pattern = _translate("nwr;")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }"
    ]
    assert pattern.injections == []


def test_translate_query_nw_no_filters() -> None:
    pattern = _translate("nw;")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node } UNION { ?_1 rdf:type osm:way }"
    ]
    assert pattern.injections == []


def test_translate_query_nr_no_filters() -> None:
    pattern = _translate("nr;")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node } UNION { ?_1 rdf:type osm:relation }"
    ]
    assert pattern.injections == []


def test_translate_query_wr_no_filters() -> None:
    pattern = _translate("wr;")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:way } UNION { ?_1 rdf:type osm:relation }"
    ]
    assert pattern.injections == []


def test_translate_query_named_output_set() -> None:
    pattern = _translate("node -> .peaks;")[0]
    assert pattern.result_variable == "?peaks1"
    assert pattern.where_clauses == ["?peaks1 rdf:type osm:node ."]


def test_translate_query_area_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _translate("area;")


# ---------------------------------------------------------------------------
# _translate_query — TagKeyFilter
# ---------------------------------------------------------------------------


def test_translate_tag_key_exists() -> None:
    pattern = _translate("node[natural];")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:natural ?_1·f0·v .",
    ]
    assert pattern.injections == []


def test_translate_tag_key_absent() -> None:
    pattern = _translate("node[!natural];")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "FILTER NOT EXISTS { ?_1 osmkey:natural ?_1·f0·v }",
    ]
    assert pattern.injections == []


def test_translate_tag_key_with_colon() -> None:
    pattern = _translate('node["geyser:type"];')[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geyser:type ?_1·f0·v .",
    ]


def test_translate_tag_key_multiple_filters() -> None:
    pattern = _translate("node[natural][name];")[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:natural ?_1·f0·v .",
        "?_1 osmkey:name ?_1·f1·v .",
    ]


# ---------------------------------------------------------------------------
# _translate_query — TagValueFilter
# ---------------------------------------------------------------------------


def test_translate_tag_value_eq() -> None:
    pattern = _translate("node[natural=peak];")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
    ]
    assert pattern.injections == []


def test_translate_tag_value_neq() -> None:
    pattern = _translate("node[natural!=peak];")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        'FILTER NOT EXISTS { ?_1 osmkey:natural "peak" }',
    ]
    assert pattern.injections == []


def test_translate_tag_value_regex() -> None:
    pattern = _translate('node[geological~"crater"];')[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geological ?_1·f0·v .",
        'FILTER(REGEX(?_1·f0·v, "crater"))',
    ]


def test_translate_tag_value_regex_case_insensitive() -> None:
    pattern = _translate('node[geological~"CRATER",i];')[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geological ?_1·f0·v .",
        'FILTER(REGEX(?_1·f0·v, "CRATER", "i"))',
    ]


def test_translate_tag_value_not_regex() -> None:
    pattern = _translate('node[geological!~"crater"];')[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geological ?_1·f0·v .",
        'FILTER(!REGEX(?_1·f0·v, "crater"))',
    ]


def test_translate_tag_value_not_regex_case_insensitive() -> None:
    pattern = _translate('node[geological!~"CRATER",i];')[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geological ?_1·f0·v .",
        'FILTER(!REGEX(?_1·f0·v, "CRATER", "i"))',
    ]


def test_translate_tag_value_escaping() -> None:
    pattern = _translate(r'node[name="say \"hello\""];')[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        r'?_1 osmkey:name "say \"hello\"" .',
    ]


# ---------------------------------------------------------------------------
# _translate_query — BboxFilter
# ---------------------------------------------------------------------------


def test_translate_bbox_filter_node() -> None:
    pattern = _translate("node(32.58870,-116.14417,32.88870,-115.84417);")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 geo:hasGeometry ?_1·f0·geom .",
        "?_1·f0·geom geo:asWKT ?_1·f0·wkt .",
        "FILTER(geof:minX(?_1·f0·wkt) <= -115.84417 && "
        "geof:maxX(?_1·f0·wkt) >= -116.14417)",
        "FILTER(geof:minY(?_1·f0·wkt) <= 32.88870 && "
        "geof:maxY(?_1·f0·wkt) >= 32.58870)",
    ]
    assert pattern.injections == []


def test_translate_bbox_filter_way() -> None:
    pattern = _translate("way(32.58870,-116.14417,32.88870,-115.84417);")[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        "?_1 geo:hasGeometry ?_1·f0·geom .",
        "?_1·f0·geom geo:asWKT ?_1·f0·wkt .",
        "FILTER(geof:minX(?_1·f0·wkt) <= -115.84417 && "
        "geof:maxX(?_1·f0·wkt) >= -116.14417)",
        "FILTER(geof:minY(?_1·f0·wkt) <= 32.88870 && "
        "geof:maxY(?_1·f0·wkt) >= 32.58870)",
    ]


def test_translate_bbox_filter_nwr() -> None:
    pattern = _translate("nwr(32.58870,-116.14417,32.88870,-115.84417);")[0]
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        "?_1 geo:hasGeometry ?_1·f0·geom .",
        "?_1·f0·geom geo:asWKT ?_1·f0·wkt .",
        "FILTER(geof:minX(?_1·f0·wkt) <= -115.84417 && "
        "geof:maxX(?_1·f0·wkt) >= -116.14417)",
        "FILTER(geof:minY(?_1·f0·wkt) <= 32.88870 && "
        "geof:maxY(?_1·f0·wkt) >= 32.58870)",
    ]


def test_translate_bbox_filter_with_tag() -> None:
    pattern = _translate(
        "node[natural=peak](32.58870,-116.14417,32.88870,-115.84417);"
    )[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
        "?_1 geo:hasGeometry ?_1·f1·geom .",
        "?_1·f1·geom geo:asWKT ?_1·f1·wkt .",
        "FILTER(geof:minX(?_1·f1·wkt) <= -115.84417 && "
        "geof:maxX(?_1·f1·wkt) >= -116.14417)",
        "FILTER(geof:minY(?_1·f1·wkt) <= 32.88870 && "
        "geof:maxY(?_1·f1·wkt) >= 32.58870)",
    ]


# ---------------------------------------------------------------------------
# _translate_query — IdFilter
# ---------------------------------------------------------------------------


def test_translate_id_filter_single_node() -> None:
    pattern = _translate("node(1);")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmnode"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "VALUES ?_1 { osmnode:1 }",
    ]
    assert pattern.injections == []


def test_translate_id_filter_multiple_ids() -> None:
    pattern = _translate("node(id:1,2,3);")[0]
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "VALUES ?_1 { osmnode:1 osmnode:2 osmnode:3 }",
    ]


def test_translate_id_filter_way() -> None:
    pattern = _translate("way(100);")[0]
    assert pattern.prefixes == {"rdf", "osm", "osmway"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        "VALUES ?_1 { osmway:100 }",
    ]


def test_translate_id_filter_nwr() -> None:
    pattern = _translate("nwr(id:1,2);")[0]
    assert pattern.prefixes == {"rdf", "osm", "osmnode", "osmway", "osmrel"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        "VALUES ?_1 { osmnode:1 osmnode:2 osmway:1 osmway:2 osmrel:1 osmrel:2 }",
    ]


# ---------------------------------------------------------------------------
# _translate_query — AroundPointFilter
# ---------------------------------------------------------------------------


def test_translate_around_point_filter_node() -> None:
    pattern = _translate("node[natural=peak](around:25000,32.73870,-115.99417);")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
        "?_1 geo:hasGeometry ?_1·f1·geom .",
        "?_1·f1·geom geo:asWKT ?_1·f1·wkt .",
        "FILTER(geof:metricDistance(?_1·f1·wkt, "
        '"POINT(-115.99417 32.73870)"^^geo:wktLiteral) <= 25000)',
    ]
    assert pattern.injections == []


def test_translate_around_point_filter_way() -> None:
    pattern = _translate("way(around:1000,51.5,-0.1);")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        "?_1 geo:hasGeometry ?_1·f0·geom .",
        "?_1·f0·geom geo:asWKT ?_1·f0·wkt .",
        "FILTER(geof:metricDistance(?_1·f0·wkt, "
        '"POINT(-0.1 51.5)"^^geo:wktLiteral) <= 1000)',
    ]


def test_translate_around_point_filter_nwr() -> None:
    pattern = _translate("nwr(around:500,40.7,-74.0);")[0]
    assert pattern.prefixes == {"rdf", "osm", "geo", "geof"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        "?_1 geo:hasGeometry ?_1·f0·geom .",
        "?_1·f0·geom geo:asWKT ?_1·f0·wkt .",
        "FILTER(geof:metricDistance(?_1·f0·wkt, "
        '"POINT(-74.0 40.7)"^^geo:wktLiteral) <= 500)',
    ]


# ---------------------------------------------------------------------------
# _translate_query — AroundLineFilter
# ---------------------------------------------------------------------------


def test_translate_around_line_filter_two_points() -> None:
    pattern = _translate(
        "node[natural=peak](around:3000,32.8253,-116.0153,32.7319,-116.0495);"
    )[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
        "?_1 geo:hasGeometry ?_1·f1·geom .",
        "?_1·f1·geom geo:asWKT ?_1·f1·wkt .",
        'FILTER(geof:metricDistance(?_1·f1·wkt, "LINESTRING(-116.0153 32.8253, '
        '-116.0495 32.7319)"^^geo:wktLiteral) <= 3000)',
    ]


def test_translate_around_line_filter_three_points() -> None:
    pattern = _translate("way(around:500,51.5,-0.1,51.6,-0.2,51.7,-0.3);")[0]
    assert pattern.prefixes == {"rdf", "osm", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        "?_1 geo:hasGeometry ?_1·f0·geom .",
        "?_1·f0·geom geo:asWKT ?_1·f0·wkt .",
        'FILTER(geof:metricDistance(?_1·f0·wkt, "LINESTRING(-0.1 51.5, -0.2 '
        '51.6, -0.3 51.7)"^^geo:wktLiteral) <= 500)',
    ]


def test_translate_around_line_filter_nwr() -> None:
    pattern = _translate("nwr(around:1000,40.0,-73.0,41.0,-74.0);")[0]
    assert pattern.prefixes == {"rdf", "osm", "geo", "geof"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        "?_1 geo:hasGeometry ?_1·f0·geom .",
        "?_1·f0·geom geo:asWKT ?_1·f0·wkt .",
        'FILTER(geof:metricDistance(?_1·f0·wkt, "LINESTRING(-73.0 40.0, '
        '-74.0 41.0)"^^geo:wktLiteral) <= 1000)',
    ]


# ---------------------------------------------------------------------------
# _translate_query — PolygonFilter
# ---------------------------------------------------------------------------


def test_translate_polygon_filter_node() -> None:
    pattern = _translate(
        'node[natural=peak](poly:"32.60 -116.12 32.78 -116.10 32.85 -115.90 32.70 '
        '-115.86 32.58 -115.95");'
    )[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
        'VALUES ?_1·f1·poly { "POLYGON((-116.12 32.60, -116.10 32.78, -115.90 32.85, '
        '-115.86 32.70, -115.95 32.58, -116.12 32.60))"^^geo:wktLiteral }',
        "?_1 geo:hasGeometry ?_1·f1·geom .",
        "?_1·f1·geom geo:asWKT ?_1·f1·wkt .",
        "FILTER(geof:sfWithin(?_1·f1·wkt, ?_1·f1·poly))",
    ]


def test_translate_polygon_filter_way() -> None:
    pattern = _translate(
        'way[natural](poly:"32.60 -116.12 32.78 -116.10 32.85 -115.90");'
    )[0]
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        "?_1 osmkey:natural ?_1·f0·v .",
        'VALUES ?_1·f1·poly { "POLYGON((-116.12 32.60, -116.10 32.78, -115.90 32.85, '
        '-116.12 32.60))"^^geo:wktLiteral }',
        "?_1 geo:hasGeometry ?_1·f1·geom .",
        "?_1·f1·geom geo:asWKT ?_1·f1·wkt .",
        "FILTER(geof:sfIntersects(?_1·f1·wkt, ?_1·f1·poly))",
    ]


def test_translate_polygon_filter_relation() -> None:
    pattern = _translate(
        'relation[natural](poly:"32.60 -116.12 32.78 -116.10 32.85 -115.90");'
    )[0]
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:relation .",
        "?_1 osmkey:natural ?_1·f0·v .",
        'VALUES ?_1·f1·poly { "POLYGON((-116.12 32.60, -116.10 32.78, -115.90 32.85, '
        '-116.12 32.60))"^^geo:wktLiteral }',
        "?_1 geo:hasGeometry ?_1·f1·geom .",
        "?_1·f1·geom geo:asWKT ?_1·f1·wkt .",
        "FILTER(geof:sfIntersects(?_1·f1·wkt, ?_1·f1·poly))",
    ]


def test_translate_polygon_filter_nwr() -> None:
    pattern = _translate('nwr(poly:"40.0 -74.0 41.0 -73.0 42.0 -72.0");')[0]
    assert pattern.prefixes == {"rdf", "osm", "geo", "geof"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        'VALUES ?_1·f0·poly { "POLYGON((-74.0 40.0, -73.0 41.0, -72.0 42.0, '
        '-74.0 40.0))"^^geo:wktLiteral }',
        "?_1 geo:hasGeometry ?_1·f0·geom .",
        "?_1·f0·geom geo:asWKT ?_1·f0·wkt .",
        "FILTER(geof:sfIntersects(?_1·f0·wkt, ?_1·f0·poly))",
    ]


# ---------------------------------------------------------------------------
# _translate_query — NewerFilter
# ---------------------------------------------------------------------------


def test_translate_newer_filter_node() -> None:
    pattern = _translate('node[natural=peak](newer:"2025-01-01T00:00:00Z");')[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "osmeta", "xsd"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
        "?_1 osmeta:timestamp ?_1·f1·ts .",
        'FILTER(?_1·f1·ts > "2025-01-01T00:00:00"^^xsd:dateTime)',
    ]


def test_translate_newer_filter_way() -> None:
    pattern = _translate('way(newer:"2024-06-15T12:30:45Z");')[0]
    assert pattern.prefixes == {"rdf", "osm", "osmeta", "xsd"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        "?_1 osmeta:timestamp ?_1·f0·ts .",
        'FILTER(?_1·f0·ts > "2024-06-15T12:30:45"^^xsd:dateTime)',
    ]


def test_translate_newer_filter_nwr() -> None:
    pattern = _translate('nwr(newer:"2023-01-01T00:00:00Z");')[0]
    assert pattern.prefixes == {"rdf", "osm", "osmeta", "xsd"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        "?_1 osmeta:timestamp ?_1·f0·ts .",
        'FILTER(?_1·f0·ts > "2023-01-01T00:00:00"^^xsd:dateTime)',
    ]


# ---------------------------------------------------------------------------
# _translate_query — UserFilter
# ---------------------------------------------------------------------------


def test_translate_user_filter_single() -> None:
    pattern = _translate('node[natural=peak](user:"Yushclay");')[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "osmeta"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
        '?_1 osmeta:user "Yushclay" .',
    ]


def test_translate_user_filter_multiple() -> None:
    pattern = _translate('way(user:"Alice","Bob");')[0]
    assert pattern.prefixes == {"rdf", "osm", "osmeta"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        'VALUES ?_1·f0·u { "Alice" "Bob" }',
        "?_1 osmeta:user ?_1·f0·u .",
    ]


def test_translate_user_filter_nwr() -> None:
    pattern = _translate('nwr(user:"TestUser");')[0]
    assert pattern.prefixes == {"rdf", "osm", "osmeta"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        '?_1 osmeta:user "TestUser" .',
    ]


# ---------------------------------------------------------------------------
# _translate_query — UidFilter
# ---------------------------------------------------------------------------


def test_translate_uid_filter_single() -> None:
    pattern = _translate("node[natural=peak](uid:23131980);")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "osmeta", "xsd"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
        '?_1 osmeta:uid "23131980"^^xsd:int .',
    ]


def test_translate_uid_filter_multiple() -> None:
    pattern = _translate("way(uid:101,202);")[0]
    assert pattern.prefixes == {"rdf", "osm", "osmeta", "xsd"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        'VALUES ?_1·f0·uid { "101"^^xsd:int "202"^^xsd:int }',
        "?_1 osmeta:uid ?_1·f0·uid .",
    ]


def test_translate_uid_filter_nwr() -> None:
    pattern = _translate("nwr(uid:12345);")[0]
    assert pattern.prefixes == {"rdf", "osm", "osmeta", "xsd"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        '?_1 osmeta:uid "12345"^^xsd:int .',
    ]


# ---------------------------------------------------------------------------
# _translate_query — AreaIdFilter
# ---------------------------------------------------------------------------


def test_translate_area_id_filter_relation() -> None:
    pattern = _translate("node[geological=meteor_crater](area:3602978650);")[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "ogc", "osmrel"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:geological "meteor_crater" .',
        "osmrel:2978650 ogc:sfContains ?_1 .",
    ]


def test_translate_area_id_filter_way() -> None:
    pattern = _translate("node[place](area:2400000100);")[0]
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "ogc", "osmway"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:place ?_1·f0·v .",
        "osmway:100 ogc:sfContains ?_1 .",
    ]


def test_translate_area_id_filter_nwr() -> None:
    pattern = _translate("nwr(area:3618375211);")[0]
    assert pattern.prefixes == {"rdf", "osm", "ogc", "osmrel"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        "osmrel:18375211 ogc:sfContains ?_1 .",
    ]


# ---------------------------------------------------------------------------
# _translate_set_filter
# ---------------------------------------------------------------------------


def test_translate_set_filter_basic() -> None:
    query = OverpassTransformer().transform(
        parse("node[geological=meteor_crater] -> .craters; node.craters;")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_1 rdf:type osm:node ."]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1", set_name="craters1")
    ]


def test_translate_set_filter_with_tag() -> None:
    query = OverpassTransformer().transform(
        parse("node[geological=meteor_crater] -> .craters; node.craters[natural=peak];")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1", set_name="craters1")
    ]


def test_translate_set_filter_multiple_intersection() -> None:
    query = OverpassTransformer().transform(
        parse("(node(1); node(2);) -> .foo; (node(2); node(3);) -> .bar; node.foo.bar;")
    )
    pattern = translate(query.statements[2])[0]
    assert pattern.result_variable == "?_5"  # Version 5 of default set
    assert pattern.where_clauses == ["?_5 rdf:type osm:node ."]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_5", set_name="foo1"),
        ValuesInjection(sparql_var="?_5", set_name="bar1"),
    ]


def test_translate_set_filter_way() -> None:
    query = OverpassTransformer().transform(
        parse("way[highway] -> .roads; way.roads[surface=asphalt];")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        '?_1 osmkey:surface "asphalt" .',
    ]
    assert pattern.injections == [ValuesInjection(sparql_var="?_1", set_name="roads1")]


# ---------------------------------------------------------------------------
# _translate_around_set_filter
# ---------------------------------------------------------------------------


def test_translate_around_set_filter_basic() -> None:
    query = OverpassTransformer().transform(
        parse("node(358781618) -> .ref; node[natural=peak](around.ref:15000);")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is True
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
        "?_1·f1·ref geo:hasGeometry ?_1·f1·refgeom .",
        "?_1·f1·refgeom geo:asWKT ?_1·f1·refwkt .",
        "?_1 geo:hasGeometry ?_1·f1·geom .",
        "?_1·f1·geom geo:asWKT ?_1·f1·wkt .",
        "FILTER(geof:metricDistance(?_1·f1·wkt, ?_1·f1·refwkt) <= 15000)",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f1·ref", set_name="ref1")
    ]


def test_translate_around_set_filter_with_default_set() -> None:
    query = OverpassTransformer().transform(
        parse("node(1); node[natural=peak](around:5000);")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_2"  # Version 2 of default set
    assert pattern.distinct is True
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "geo", "geof"}
    assert pattern.where_clauses == [
        "?_2 rdf:type osm:node .",
        '?_2 osmkey:natural "peak" .',
        "?_2·f1·ref geo:hasGeometry ?_2·f1·refgeom .",
        "?_2·f1·refgeom geo:asWKT ?_2·f1·refwkt .",
        "?_2 geo:hasGeometry ?_2·f1·geom .",
        "?_2·f1·geom geo:asWKT ?_2·f1·wkt .",
        "FILTER(geof:metricDistance(?_2·f1·wkt, ?_2·f1·refwkt) <= 5000)",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_2·f1·ref", set_name="_1")
    ]


def test_translate_around_set_filter_way() -> None:
    query = OverpassTransformer().transform(
        parse("node[amenity=cafe] -> .cafes; way[highway](around.cafes:100);")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is True
    assert pattern.where_clauses[0] == "?_1 rdf:type osm:way ."
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f1·ref", set_name="cafes1")
    ]


def test_translate_around_set_filter_cross_type() -> None:
    query = OverpassTransformer().transform(
        parse(
            "node[geological=meteor_crater] -> .craters;"
            "node[natural=geyser](around.craters:100000);"
        )
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is True
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "geyser" .',
        "?_1·f1·ref geo:hasGeometry ?_1·f1·refgeom .",
        "?_1·f1·refgeom geo:asWKT ?_1·f1·refwkt .",
        "?_1 geo:hasGeometry ?_1·f1·geom .",
        "?_1·f1·geom geo:asWKT ?_1·f1·wkt .",
        "FILTER(geof:metricDistance(?_1·f1·wkt, ?_1·f1·refwkt) <= 100000)",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f1·ref", set_name="craters1")
    ]


# ---------------------------------------------------------------------------
# _translate_area_set_filter
# ---------------------------------------------------------------------------


def test_translate_area_set_filter_basic() -> None:
    query = OverpassTransformer().transform(
        parse(
            'way["boundary"="administrative"] -> .area; node[amenity=cafe](area.area);'
        )
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "ogc"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:amenity "cafe" .',
        "?_1·f1·area ogc:sfContains ?_1 .",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f1·area", set_name="area1")
    ]


def test_translate_area_set_filter_with_default_set() -> None:
    query = OverpassTransformer().transform(
        parse('relation["boundary"="administrative"]; node[amenity=hospital](area);')
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_2"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "ogc"}
    assert pattern.where_clauses == [
        "?_2 rdf:type osm:node .",
        '?_2 osmkey:amenity "hospital" .',
        "?_2·f1·area ogc:sfContains ?_2 .",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_2·f1·area", set_name="_1")
    ]


def test_translate_area_set_filter_way() -> None:
    query = OverpassTransformer().transform(
        parse('relation["boundary"="protected_area"] -> .pa; way[landuse](area.pa);')
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.where_clauses[0] == "?_1 rdf:type osm:way ."
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f1·area", set_name="pa1")
    ]


def test_translate_area_set_filter_nwr() -> None:
    query = OverpassTransformer().transform(
        parse(
            'relation["boundary"="national_park"] -> .parks; nwr[tourism](area.parks);'
        )
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey", "ogc"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node }"
        " UNION { ?_1 rdf:type osm:way }"
        " UNION { ?_1 rdf:type osm:relation }",
        "?_1 osmkey:tourism ?_1·f0·v .",
        "?_1·f1·area ogc:sfContains ?_1 .",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f1·area", set_name="parks1")
    ]


# ---------------------------------------------------------------------------
# _translate_recurse_filter
# ---------------------------------------------------------------------------


def test_translate_recurse_filter_w() -> None:
    query = OverpassTransformer().transform(parse("way(100); node(w);"))
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_2"
    assert pattern.distinct is True
    assert pattern.prefixes == {"rdf", "osm", "osmway"}
    assert pattern.where_clauses == [
        "?_2 rdf:type osm:node .",
        "?_2·f0·input osmway:member ?_2·f0·m .",
        "?_2·f0·m osmway:member_id ?_2 .",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_2·f0·input", set_name="_1")
    ]


def test_translate_recurse_filter_w_named_set() -> None:
    query = OverpassTransformer().transform(
        parse("way[highway=cycleway] -> .ways; node(w.ways);")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is True
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1·f0·input osmway:member ?_1·f0·m .",
        "?_1·f0·m osmway:member_id ?_1 .",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f0·input", set_name="ways1")
    ]


def test_translate_recurse_filter_r() -> None:
    query = OverpassTransformer().transform(parse("relation(10000); way(r);"))
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_2"
    assert pattern.distinct is True
    assert pattern.prefixes == {"rdf", "osm", "osmrel"}
    assert pattern.where_clauses == [
        "?_2 rdf:type osm:way .",
        "?_2·f0·input osmrel:member ?_2·f0·m .",
        "?_2·f0·m osmrel:member_id ?_2 .",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_2·f0·input", set_name="_1")
    ]


def test_translate_recurse_filter_r_with_role() -> None:
    query = OverpassTransformer().transform(parse('relation(10000); way(r:"outer");'))
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_2"
    assert pattern.distinct is True
    assert pattern.where_clauses == [
        "?_2 rdf:type osm:way .",
        "?_2·f0·input osmrel:member ?_2·f0·m .",
        "?_2·f0·m osmrel:member_id ?_2 .",
        '?_2·f0·m osmrel:member_role "outer" .',
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_2·f0·input", set_name="_1")
    ]


def test_translate_recurse_filter_bw() -> None:
    query = OverpassTransformer().transform(parse("way(100); relation(bw);"))
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_2"
    assert pattern.distinct is True
    assert pattern.prefixes == {"rdf", "osm", "osmrel"}
    assert pattern.where_clauses == [
        "?_2 rdf:type osm:relation .",
        "?_2·f0·m osmrel:member_id ?_2·f0·input .",
        "?_2 osmrel:member ?_2·f0·m .",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_2·f0·input", set_name="_1")
    ]


def test_translate_recurse_filter_br() -> None:
    query = OverpassTransformer().transform(
        parse("relation[type=route] -> .routes; relation(br.routes);")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is True
    assert pattern.prefixes == {"rdf", "osm", "osmrel"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:relation .",
        "?_1·f0·m osmrel:member_id ?_1·f0·input .",
        "?_1 osmrel:member ?_1·f0·m .",
    ]
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f0·input", set_name="routes1")
    ]


def test_translate_recurse_filter_bn_unimplemented() -> None:
    query = OverpassTransformer().transform(parse("node(260904); way(bn);"))
    with pytest.raises(UnimplementedFeatureError):
        translate(query.statements[1])


# ---------------------------------------------------------------------------
# _translate_way_count_filter
# ---------------------------------------------------------------------------


def test_translate_way_count_filter_exact() -> None:
    query = OverpassTransformer().transform(parse("way[highway]; node(way_cnt:1);"))
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_2"
    assert pattern.distinct is True
    assert pattern.prefixes == {"rdf", "osm", "osmway"}
    # Should have: type filter, way join, subquery, count filter
    assert "?_2 rdf:type osm:node ." in pattern.where_clauses
    assert "?_2·f0·way osmway:member ?_2·f0·m ." in pattern.where_clauses
    assert "?_2·f0·m osmway:member_id ?_2 ." in pattern.where_clauses
    # Check for subquery presence
    assert any(
        "SELECT ?_2 (COUNT(DISTINCT ?_2·f0·way)" in clause
        for clause in pattern.where_clauses
    )
    assert any("FILTER(?_2·f0·cnt = 1)" in clause for clause in pattern.where_clauses)
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_2·f0·way", set_name="_1", must_materialize=True)
    ]


def test_translate_way_count_filter_min() -> None:
    query = OverpassTransformer().transform(
        parse("way[highway] -> .ways; node(way_cnt.ways:2-);")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is True
    # Check for >= 2 filter
    assert any("FILTER(?_1·f0·cnt >= 2)" in clause for clause in pattern.where_clauses)
    assert pattern.injections == [
        ValuesInjection(
            sparql_var="?_1·f0·way", set_name="ways1", must_materialize=True
        )
    ]


def test_translate_way_count_filter_range() -> None:
    query = OverpassTransformer().transform(
        parse("way[highway] -> .w; node(way_cnt.w:1-4);")
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is True
    # Check for range filter
    assert any(
        "FILTER(?_1·f0·cnt >= 1 && ?_1·f0·cnt <= 4)" in clause
        for clause in pattern.where_clauses
    )
    assert pattern.injections == [
        ValuesInjection(sparql_var="?_1·f0·way", set_name="w1", must_materialize=True)
    ]


# ---------------------------------------------------------------------------
# _translate_pivot_filter
# ---------------------------------------------------------------------------


def test_translate_pivot_filter_default_set() -> None:
    query = OverpassTransformer().transform(parse('area["name"="Paris"]; way(pivot);'))
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_2"
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_2 rdf:type osm:way ."]
    assert pattern.injections == [ValuesInjection(sparql_var="?_2", set_name="_1")]


def test_translate_pivot_filter_named_set() -> None:
    query = OverpassTransformer().transform(
        parse('area["name"="Berlin"] -> .city; way(pivot.city);')
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_1 rdf:type osm:way ."]
    assert pattern.injections == [ValuesInjection(sparql_var="?_1", set_name="city1")]


def test_translate_pivot_filter_with_tag() -> None:
    query = OverpassTransformer().transform(
        parse('area["name"="London"] -> .area; way[highway=primary](pivot.area);')
    )
    pattern = translate(query.statements[1])[0]
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:way .",
        '?_1 osmkey:highway "primary" .',
    ]
    assert pattern.injections == [ValuesInjection(sparql_var="?_1", set_name="area1")]
