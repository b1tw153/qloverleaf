from dataclasses import dataclass, field

from qloverleaf.exceptions import UnimplementedFeatureError
from qloverleaf.transformer import (
    _NUMERIC_TYPES,
    AbsEvaluator,
    AddEvaluator,
    AddOperator,
    BinaryEvaluator,
    CompareEvaluator,
    CompareOperator,
    ConversionEvaluator,
    ConversionFunction,
    CoordinateEvaluator,
    CountByRoleEvaluator,
    CountEvaluator,
    CountMembersEvaluator,
    CountTagsEvaluator,
    Evaluator,
    IsClosedEvaluator,
    IsTagEvaluator,
    LengthEvaluator,
    LiteralEvaluator,
    MetadataEvaluator,
    MinMaxEvaluator,
    MultiplyEvaluator,
    ScalarType,
    SuffixEvaluator,
    SumEvaluator,
    TagValueEvaluator,
    TernaryEvaluator,
    TypeCheckEvaluator,
    TypeCheckFunction,
    UnaryEvaluator,
    UnaryOperator,
    UniqueEvaluator,
    ValEvaluator,
)
from qloverleaf.translator import SetInjection


@dataclass
class Subquery:
    select_clause: str
    group_by: str | None = None
    where_clauses: list[str] = field(default_factory=list)
    injections: list[SetInjection] = field(default_factory=list)


@dataclass
class EvaluatorPattern:
    expression: str
    prefixes: set[str] = field(default_factory=set)
    clauses: list[str] = field(default_factory=list)
    subqueries: list[Subquery] = field(default_factory=list)


def translate_evaluator(evaluator: Evaluator, element_var: str) -> EvaluatorPattern:
    """Translate an evaluator IR node into an EvaluatorPattern.

    element_var is the SPARQL variable (with ? prefix) that represents the current
    OSM element in the enclosing SparqlPattern — e.g. "?_1" or "?craters1".
    Evaluators that reference element attributes use it as the subject of their
    triple patterns.
    """
    # ternary_expr
    if isinstance(evaluator, TernaryEvaluator):
        return _translate_ternary(evaluator, element_var)
    # or_expr
    # and_expr
    if isinstance(evaluator, BinaryEvaluator):
        return _translate_binary(evaluator, element_var)
    # not_expr
    if isinstance(evaluator, UnaryEvaluator):
        return _translate_unary(evaluator, element_var)
    # compare_expr
    if isinstance(evaluator, CompareEvaluator):
        return _translate_compare(evaluator, element_var)
    # add_expr
    if isinstance(evaluator, AddEvaluator):
        return _translate_add(evaluator, element_var)
    # mul_expr
    if isinstance(evaluator, MultiplyEvaluator):
        return _translate_multiply(evaluator, element_var)
    # unary_expr
    # literal_expr
    if isinstance(evaluator, LiteralEvaluator):
        return _translate_literal(evaluator)
    # grouped_expr: no IR class; transformer passes inner evaluator through
    # id_expr
    # type_expr
    # tag_value_expr
    if isinstance(evaluator, TagValueEvaluator):
        return _translate_tag_value(evaluator, element_var)
    # is_tag_expr
    if isinstance(evaluator, IsTagEvaluator):
        return _translate_is_tag(evaluator, element_var)
    # keys_expr: unsupported
    # generic_tag_expr: unsupported
    # version_expr
    # timestamp_expr
    # changeset_expr
    # uid_expr
    # user_expr
    if isinstance(evaluator, MetadataEvaluator):
        return _translate_metadata(evaluator, element_var)
    # count_tags_expr
    if isinstance(evaluator, CountTagsEvaluator):
        return _translate_count_tags(evaluator, element_var)
    # count_members_expr
    # count_distinct_members_expr (CountMembersEvaluator with distinct=True)
    if isinstance(evaluator, CountMembersEvaluator):
        return _translate_count_members(evaluator, element_var)
    # count_by_role_expr
    # count_distinct_by_role_expr (CountByRoleEvaluator with distinct=True)
    if isinstance(evaluator, CountByRoleEvaluator):
        return _translate_count_by_role(evaluator, element_var)
    # is_closed_expr
    if isinstance(evaluator, IsClosedEvaluator):
        return _translate_is_closed(evaluator, element_var)
    # lat_expr
    # lon_expr
    if isinstance(evaluator, CoordinateEvaluator):
        return _translate_coordinate(evaluator, element_var)
    # geom_expr: unsupported
    # length_expr
    if isinstance(evaluator, LengthEvaluator):
        return _translate_length(evaluator, element_var)
    # center_expr: unsupported
    # trace_expr: unsupported
    # hull_expr: unsupported
    # pt_expr: unsupported
    # lstr_expr: unsupported
    # poly_expr: unsupported
    # per_member_expr: unsupported
    # per_vertex_expr: unsupported
    # pos_expr: unsupported
    # mtype_expr: unsupported
    # ref_expr: unsupported
    # role_expr: unsupported
    # angle_expr: unsupported
    # number_expr
    # date_expr
    if isinstance(evaluator, ConversionEvaluator):
        return _translate_conversion(evaluator, element_var)
    # suffix_expr
    if isinstance(evaluator, SuffixEvaluator):
        return _translate_suffix(evaluator, element_var)
    # abs_expr
    if isinstance(evaluator, AbsEvaluator):
        return _translate_abs(evaluator, element_var)
    # is_number_expr
    # is_date_expr
    if isinstance(evaluator, TypeCheckEvaluator):
        return _translate_type_check(evaluator, element_var)
    # unique_expr
    if isinstance(evaluator, UniqueEvaluator):
        return _translate_unique(evaluator, element_var)
    # min_expr
    # max_expr
    if isinstance(evaluator, MinMaxEvaluator):
        return _translate_minmax(evaluator, element_var)
    # sum_expr
    if isinstance(evaluator, SumEvaluator):
        return _translate_sum(evaluator, element_var)
    # set_expr: unsupported
    # gcat_expr: unsupported
    # count_expr
    if isinstance(evaluator, CountEvaluator):
        return _translate_count(evaluator)
    # lrs_in_expr: unsupported
    # lrs_isect_expr: unsupported
    # lrs_union_expr: unsupported
    # lrs_min_expr: unsupported
    # lrs_max_expr: unsupported
    # val_expr
    if isinstance(evaluator, ValEvaluator):
        return _translate_val(evaluator)
    raise NotImplementedError(f"No evaluator translator for {type(evaluator).__name__}")


# ternary_expr
def _translate_ternary(
    evaluator: TernaryEvaluator, element_var: str
) -> EvaluatorPattern:
    condition_pattern = translate_evaluator(evaluator.condition, element_var)
    true_pattern = translate_evaluator(evaluator.true_expression, element_var)
    false_pattern = translate_evaluator(evaluator.false_expression, element_var)
    expression = (
        f"IF({condition_pattern.expression}, "
        f"{true_pattern.expression}, "
        f"{false_pattern.expression})"
    )
    prefixes = (
        condition_pattern.prefixes | true_pattern.prefixes | false_pattern.prefixes
    )
    clauses = condition_pattern.clauses + true_pattern.clauses + false_pattern.clauses
    subqueries = (
        condition_pattern.subqueries
        + true_pattern.subqueries
        + false_pattern.subqueries
    )
    return EvaluatorPattern(
        expression=expression, prefixes=prefixes, clauses=clauses, subqueries=subqueries
    )


# or_expr
# and_expr
def _translate_binary(evaluator: BinaryEvaluator, element_var: str) -> EvaluatorPattern:
    operand_patterns = [
        translate_evaluator(operand, element_var) for operand in evaluator.operands
    ]
    op = evaluator.operator.value
    operand_expressions = [pattern.expression for pattern in operand_patterns]
    expression = "(" + f") {op} (".join(operand_expressions) + ")"
    prefixes = set.union(*(pattern.prefixes for pattern in operand_patterns))
    clauses = [clause for pattern in operand_patterns for clause in pattern.clauses]
    subqueries = [
        subquery for pattern in operand_patterns for subquery in pattern.subqueries
    ]
    return EvaluatorPattern(
        expression=expression, prefixes=prefixes, clauses=clauses, subqueries=subqueries
    )


# not_expr
# unary_expr (NEGATE)
def _translate_unary(evaluator: UnaryEvaluator, element_var: str) -> EvaluatorPattern:
    inner = translate_evaluator(evaluator.operand, element_var)
    op = "!" if evaluator.operator == UnaryOperator.NOT else "-"
    return EvaluatorPattern(
        expression=f"{op}({inner.expression})",
        prefixes=inner.prefixes,
        clauses=inner.clauses,
        subqueries=inner.subqueries,
    )


# Overpass uses == for equality; SPARQL uses =. All other operators map directly.
_COMPARE_OP_SPARQL: dict[CompareOperator, str] = {
    CompareOperator.EQUAL: "=",
    CompareOperator.NOT_EQUAL: "!=",
    CompareOperator.LESS_THAN: "<",
    CompareOperator.LESS_THAN_OR_EQUAL: "<=",
    CompareOperator.GREATER_THAN: ">",
    CompareOperator.GREATER_THAN_OR_EQUAL: ">=",
}


# compare_expr
def _translate_compare(
    evaluator: CompareEvaluator, element_var: str
) -> EvaluatorPattern:
    left_pattern = translate_evaluator(evaluator.left_operand, element_var)
    right_pattern = translate_evaluator(evaluator.right_operand, element_var)
    op = _COMPARE_OP_SPARQL[evaluator.operator]
    expression = f"({left_pattern.expression}) {op} ({right_pattern.expression})"
    prefixes = left_pattern.prefixes | right_pattern.prefixes
    clauses = left_pattern.clauses + right_pattern.clauses
    subqueries = left_pattern.subqueries + right_pattern.subqueries
    return EvaluatorPattern(
        expression=expression, prefixes=prefixes, clauses=clauses, subqueries=subqueries
    )


# add_expr
def _translate_add(evaluator: AddEvaluator, element_var: str) -> EvaluatorPattern:
    left_pattern = translate_evaluator(evaluator.left_operand, element_var)
    right_pattern = translate_evaluator(evaluator.right_operand, element_var)
    prefixes = left_pattern.prefixes | right_pattern.prefixes
    clauses = left_pattern.clauses + right_pattern.clauses
    subqueries = left_pattern.subqueries + right_pattern.subqueries
    if (
        evaluator.operator == AddOperator.ADD
        and evaluator.output_type == ScalarType.LITERAL
    ):
        # Both operands are strings: Overpass + is string concatenation
        expression = f"CONCAT({left_pattern.expression}, {right_pattern.expression})"
    else:
        op = evaluator.operator.value
        expression = f"({left_pattern.expression}) {op} ({right_pattern.expression})"
    return EvaluatorPattern(
        expression=expression, prefixes=prefixes, clauses=clauses, subqueries=subqueries
    )


# mul_expr
def _translate_multiply(
    evaluator: MultiplyEvaluator, element_var: str
) -> EvaluatorPattern:
    left_pattern = translate_evaluator(evaluator.left_operand, element_var)
    right_pattern = translate_evaluator(evaluator.right_operand, element_var)
    op = evaluator.operator.value
    expression = f"({left_pattern.expression}) {op} ({right_pattern.expression})"
    prefixes = left_pattern.prefixes | right_pattern.prefixes
    clauses = left_pattern.clauses + right_pattern.clauses
    subqueries = left_pattern.subqueries + right_pattern.subqueries
    return EvaluatorPattern(
        expression=expression, prefixes=prefixes, clauses=clauses, subqueries=subqueries
    )


# unary_expr (UnaryEvaluator with NEGATE; see _translate_unary)


# literal_expr
def _translate_literal(evaluator: LiteralEvaluator) -> EvaluatorPattern:
    # Numeric types emit the value as a bare SPARQL literal (no quotes).
    # String literals are quoted. ISO datetime strings are emitted as typed
    # xsd:dateTime literals.
    if evaluator.output_type in _NUMERIC_TYPES:
        return EvaluatorPattern(expression=evaluator.value)
    if evaluator.output_type == ScalarType.DATETIME:
        escaped = evaluator.value.replace("\\", "\\\\").replace('"', '\\"')
        return EvaluatorPattern(
            expression=f'"{escaped}"^^xsd:dateTime',
            prefixes={"xsd"},
        )
    # ScalarType.LITERAL and any other/indeterminate type: plain quoted string
    escaped = evaluator.value.replace("\\", "\\\\").replace('"', '\\"')
    return EvaluatorPattern(expression=f'"{escaped}"')


# grouped_expr: no IR class; transformer passes inner evaluator through

# id_expr (MetadataEvaluator; see _translate_metadata)
# type_expr (MetadataEvaluator; see _translate_metadata)


# tag_value_expr
def _translate_tag_value(
    evaluator: TagValueEvaluator, element_var: str
) -> EvaluatorPattern:
    # TODO: translate tag value evaluator (t["key"])
    raise UnimplementedFeatureError(
        "tag value evaluator is not implemented", evaluator.token
    )


# is_tag_expr
def _translate_is_tag(evaluator: IsTagEvaluator, element_var: str) -> EvaluatorPattern:
    # TODO: translate is_tag evaluator
    raise UnimplementedFeatureError(
        "is_tag evaluator is not implemented", evaluator.token
    )


# keys_expr: unsupported
# generic_tag_expr: unsupported


# version_expr
# timestamp_expr
# changeset_expr
# uid_expr
# user_expr
def _translate_metadata(
    evaluator: MetadataEvaluator, element_var: str
) -> EvaluatorPattern:
    # TODO: translate metadata evaluator (id, type, version, timestamp, changeset,
    #   uid, user); dispatch on evaluator.attribute
    raise UnimplementedFeatureError(
        "metadata evaluator is not implemented", evaluator.token
    )


# count_tags_expr
def _translate_count_tags(
    evaluator: CountTagsEvaluator, element_var: str
) -> EvaluatorPattern:
    # TODO: translate count_tags evaluator
    raise UnimplementedFeatureError(
        "count_tags evaluator is not implemented", evaluator.token
    )


# count_members_expr
# count_distinct_members_expr (CountMembersEvaluator with distinct=True)
def _translate_count_members(
    evaluator: CountMembersEvaluator, element_var: str
) -> EvaluatorPattern:
    # TODO: translate count_members evaluator; dispatch on evaluator.distinct
    raise UnimplementedFeatureError(
        "count_members evaluator is not implemented", evaluator.token
    )


# count_by_role_expr
# count_distinct_by_role_expr (CountByRoleEvaluator with distinct=True)
def _translate_count_by_role(
    evaluator: CountByRoleEvaluator, element_var: str
) -> EvaluatorPattern:
    # TODO: translate count_by_role evaluator; dispatch on evaluator.distinct
    raise UnimplementedFeatureError(
        "count_by_role evaluator is not implemented", evaluator.token
    )


# is_closed_expr
def _translate_is_closed(
    evaluator: IsClosedEvaluator, element_var: str
) -> EvaluatorPattern:
    # TODO: translate is_closed evaluator
    raise UnimplementedFeatureError(
        "is_closed evaluator is not implemented", evaluator.token
    )


# lat_expr
# lon_expr
def _translate_coordinate(
    evaluator: CoordinateEvaluator, element_var: str
) -> EvaluatorPattern:
    # TODO: translate coordinate evaluator (lat(), lon())
    # Note: dispatch on evaluator.axis
    raise UnimplementedFeatureError(
        "coordinate evaluator is not implemented", evaluator.token
    )


# geom_expr: unsupported


# length_expr
def _translate_length(evaluator: LengthEvaluator, element_var: str) -> EvaluatorPattern:
    # TODO: translate length evaluator
    raise UnimplementedFeatureError(
        "length evaluator is not implemented", evaluator.token
    )


# center_expr: unsupported
# trace_expr: unsupported
# hull_expr: unsupported
# pt_expr: unsupported
# lstr_expr: unsupported
# poly_expr: unsupported
# per_member_expr: unsupported
# per_vertex_expr: unsupported
# pos_expr: unsupported
# mtype_expr: unsupported
# ref_expr: unsupported
# role_expr: unsupported
# angle_expr: unsupported


# number_expr
# date_expr
def _translate_conversion(
    evaluator: ConversionEvaluator, element_var: str
) -> EvaluatorPattern:
    inner_pattern = translate_evaluator(evaluator.operand, element_var)
    if evaluator.function == ConversionFunction.NUMBER:
        expression = f"xsd:double(str({inner_pattern.expression}))"
    else:
        # ConversionFunction.DATE: construct a typed xsd:dateTime literal
        expression = f"STRDT(str({inner_pattern.expression}), xsd:dateTime)"
    return EvaluatorPattern(
        expression=expression,
        prefixes=inner_pattern.prefixes | {"xsd"},
        clauses=inner_pattern.clauses,
        subqueries=inner_pattern.subqueries,
    )


# suffix_expr
def _translate_suffix(evaluator: SuffixEvaluator, element_var: str) -> EvaluatorPattern:
    # Approximation: strips the leading numeric prefix and returns the remainder.
    # Diverges from Overpass in two ways: Overpass strips whitespace between the
    # numeric prefix and the suffix ("734 m" -> "m", not " m"), and returns "" for
    # strings with no numeric prefix rather than returning the string unchanged.
    # The \\\\. in Python source produces \\. in the SPARQL text, which SPARQL
    # parses as the regex escape \. (literal dot).
    inner_pattern = translate_evaluator(evaluator.operand, element_var)
    expression = (
        f"REPLACE({inner_pattern.expression},"
        f' "^-?[0-9]+(\\\\.[0-9]+)?([eE][+-]?[0-9]+)?", "")'
    )
    return EvaluatorPattern(
        expression=expression,
        prefixes=inner_pattern.prefixes,
        clauses=inner_pattern.clauses,
        subqueries=inner_pattern.subqueries,
    )


# abs_expr
def _translate_abs(evaluator: AbsEvaluator, element_var: str) -> EvaluatorPattern:
    inner_pattern = translate_evaluator(evaluator.operand, element_var)
    expression = f"ABS({inner_pattern.expression})"
    return EvaluatorPattern(
        expression=expression,
        prefixes=inner_pattern.prefixes,
        clauses=inner_pattern.clauses,
        subqueries=inner_pattern.subqueries,
    )


# is_number_expr
# is_date_expr
def _translate_type_check(
    evaluator: TypeCheckEvaluator, element_var: str
) -> EvaluatorPattern:
    inner_pattern = translate_evaluator(evaluator.operand, element_var)
    if evaluator.function == TypeCheckFunction.IS_NUMBER:
        # Approximation: Overpass uses strtod() semantics, which also accepts
        # scientific notation, leading whitespace, leading +, trailing decimal,
        # and leading decimal. The \\\\. produces \\. in SPARQL text (literal dot).
        regex = '"^-?[0-9]+(\\\\.[0-9]+)?$"'
    else:
        # TypeCheckFunction.IS_DATE
        # Approximation: only accepts the Z timezone suffix; offset forms (+01:00
        # etc.) return false negatives. Month range validation is not replicated.
        regex = (
            '"^[0-9]{4}(-[0-9]{2}(-[0-9]{2}([T ][0-9]{2}:[0-9]{2}:[0-9]{2}Z?)?)?)?$"'
        )
    expression = f"REGEX(str({inner_pattern.expression}), {regex})"
    return EvaluatorPattern(
        expression=expression,
        prefixes=inner_pattern.prefixes,
        clauses=inner_pattern.clauses,
        subqueries=inner_pattern.subqueries,
    )


# unique_expr
def _translate_unique(evaluator: UniqueEvaluator, element_var: str) -> EvaluatorPattern:
    # TODO: translate unique evaluator
    raise UnimplementedFeatureError(
        "unique evaluator is not implemented", evaluator.token
    )


# min_expr
# max_expr
def _translate_minmax(evaluator: MinMaxEvaluator, element_var: str) -> EvaluatorPattern:
    # TODO: translate min max evaluator (min(), max())
    # Note: dispatch on evaluator.operator
    raise UnimplementedFeatureError(
        "min max evaluator is not implemented", evaluator.token
    )


# sum_expr
def _translate_sum(evaluator: SumEvaluator, element_var: str) -> EvaluatorPattern:
    # TODO: translate sum evaluator (set_name.sum(evaluator))
    raise UnimplementedFeatureError("sum evaluator is not implemented", evaluator.token)


# set_expr: unsupported
# gcat_expr: unsupported


# count_expr
def _translate_count(evaluator: CountEvaluator) -> EvaluatorPattern:
    # TODO: translate count evaluator (set_name.count(type))
    raise UnimplementedFeatureError(
        "count evaluator is not implemented", evaluator.token
    )


# lrs_in_expr: unsupported
# lrs_isect_expr: unsupported
# lrs_union_expr: unsupported
# lrs_min_expr: unsupported
# lrs_max_expr: unsupported


# val_expr
def _translate_val(evaluator: ValEvaluator) -> EvaluatorPattern:
    # TODO: translate val evaluator (set_name.val)
    raise UnimplementedFeatureError("val evaluator is not implemented", evaluator.token)
