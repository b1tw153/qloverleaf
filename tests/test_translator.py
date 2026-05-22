import pytest

from qloverleaf.exceptions import UnimplementedFeatureError
from qloverleaf.parser import parse
from qloverleaf.transform import OverpassTransformer
from qloverleaf.translator import SparqlPattern, translate


def _translate(text: str) -> SparqlPattern:
    query = OverpassTransformer().transform(parse(text))
    return translate(query.statements[0])


# ---------------------------------------------------------------------------
# _translate_query — no filters
# ---------------------------------------------------------------------------


def test_translate_query_node_no_filters() -> None:
    pattern = _translate("node;")
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_1 rdf:type osm:node ."]
    assert pattern.injections == []


def test_translate_query_way_no_filters() -> None:
    pattern = _translate("way;")
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_1 rdf:type osm:way ."]
    assert pattern.injections == []


def test_translate_query_relation_no_filters() -> None:
    pattern = _translate("relation;")
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == ["?_1 rdf:type osm:relation ."]
    assert pattern.injections == []


def test_translate_query_nwr_no_filters() -> None:
    pattern = _translate("nwr;")
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
    pattern = _translate("nw;")
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node } UNION { ?_1 rdf:type osm:way }"
    ]
    assert pattern.injections == []


def test_translate_query_nr_no_filters() -> None:
    pattern = _translate("nr;")
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:node } UNION { ?_1 rdf:type osm:relation }"
    ]
    assert pattern.injections == []


def test_translate_query_wr_no_filters() -> None:
    pattern = _translate("wr;")
    assert pattern.result_variable == "?_1"
    assert pattern.distinct is False
    assert pattern.prefixes == {"rdf", "osm"}
    assert pattern.where_clauses == [
        "{ ?_1 rdf:type osm:way } UNION { ?_1 rdf:type osm:relation }"
    ]
    assert pattern.injections == []


def test_translate_query_named_output_set() -> None:
    pattern = _translate("node -> .peaks;")
    assert pattern.result_variable == "?peaks1"
    assert pattern.where_clauses == ["?peaks1 rdf:type osm:node ."]


def test_translate_query_area_raises() -> None:
    with pytest.raises(UnimplementedFeatureError):
        _translate("area;")


# ---------------------------------------------------------------------------
# _translate_query — TagKeyFilter
# ---------------------------------------------------------------------------


def test_translate_tag_key_exists() -> None:
    pattern = _translate("node[natural];")
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:natural ?_1·f0·v .",
    ]
    assert pattern.injections == []


def test_translate_tag_key_absent() -> None:
    pattern = _translate("node[!natural];")
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "FILTER NOT EXISTS { ?_1 osmkey:natural ?_1·f0·v }",
    ]
    assert pattern.injections == []


def test_translate_tag_key_with_colon() -> None:
    pattern = _translate('node["geyser:type"];')
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geyser:type ?_1·f0·v .",
    ]


def test_translate_tag_key_multiple_filters() -> None:
    pattern = _translate("node[natural][name];")
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:natural ?_1·f0·v .",
        "?_1 osmkey:name ?_1·f1·v .",
    ]


# ---------------------------------------------------------------------------
# _translate_query — TagValueFilter
# ---------------------------------------------------------------------------


def test_translate_tag_value_eq() -> None:
    pattern = _translate("node[natural=peak];")
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        '?_1 osmkey:natural "peak" .',
    ]
    assert pattern.injections == []


def test_translate_tag_value_neq() -> None:
    pattern = _translate("node[natural!=peak];")
    assert pattern.result_variable == "?_1"
    assert pattern.prefixes == {"rdf", "osm", "osmkey"}
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        'FILTER NOT EXISTS { ?_1 osmkey:natural "peak" }',
    ]
    assert pattern.injections == []


def test_translate_tag_value_regex() -> None:
    pattern = _translate('node[geological~"crater"];')
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geological ?_1·f0·v .",
        'FILTER(REGEX(?_1·f0·v, "crater"))',
    ]


def test_translate_tag_value_regex_case_insensitive() -> None:
    pattern = _translate('node[geological~"CRATER",i];')
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geological ?_1·f0·v .",
        'FILTER(REGEX(?_1·f0·v, "CRATER", "i"))',
    ]


def test_translate_tag_value_not_regex() -> None:
    pattern = _translate('node[geological!~"crater"];')
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geological ?_1·f0·v .",
        'FILTER(!REGEX(?_1·f0·v, "crater"))',
    ]


def test_translate_tag_value_not_regex_case_insensitive() -> None:
    pattern = _translate('node[geological!~"CRATER",i];')
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        "?_1 osmkey:geological ?_1·f0·v .",
        'FILTER(!REGEX(?_1·f0·v, "CRATER", "i"))',
    ]


def test_translate_tag_value_escaping() -> None:
    pattern = _translate(r'node[name="say \"hello\""];')
    assert pattern.where_clauses == [
        "?_1 rdf:type osm:node .",
        r'?_1 osmkey:name "say \"hello\"" .',
    ]
