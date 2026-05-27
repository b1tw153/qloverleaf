from dataclasses import dataclass, field

from qloverleaf.exceptions import UnimplementedFeatureError
from qloverleaf.transformer import (
    AbsEvaluator,
    AddEvaluator,
    BinaryEvaluator,
    CompareEvaluator,
    ConversionEvaluator,
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
    SuffixEvaluator,
    SumEvaluator,
    TagValueEvaluator,
    TernaryEvaluator,
    TypeCheckEvaluator,
    UnaryEvaluator,
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


def translate_evaluator(evaluator: Evaluator) -> EvaluatorPattern:
    # TODO: add element_var parameter (result_variable of the enclosing SparqlPattern)
    # ternary_expr
    if isinstance(evaluator, TernaryEvaluator):
        return _translate_ternary(evaluator)
    # or_expr
    # and_expr
    if isinstance(evaluator, BinaryEvaluator):
        return _translate_binary(evaluator)
    # not_expr
    if isinstance(evaluator, UnaryEvaluator):
        return _translate_unary(evaluator)
    # compare_expr
    if isinstance(evaluator, CompareEvaluator):
        return _translate_compare(evaluator)
    # add_expr
    if isinstance(evaluator, AddEvaluator):
        return _translate_add(evaluator)
    # mul_expr
    if isinstance(evaluator, MultiplyEvaluator):
        return _translate_multiply(evaluator)
    # unary_expr
    # literal_expr
    if isinstance(evaluator, LiteralEvaluator):
        return _translate_literal(evaluator)
    # grouped_expr: no IR class; transformer passes inner evaluator through
    # id_expr
    # type_expr
    # tag_value_expr
    if isinstance(evaluator, TagValueEvaluator):
        return _translate_tag_value(evaluator)
    # is_tag_expr
    if isinstance(evaluator, IsTagEvaluator):
        return _translate_is_tag(evaluator)
    # keys_expr: unsupported
    # generic_tag_expr: unsupported
    # version_expr
    # timestamp_expr
    # changeset_expr
    # uid_expr
    # user_expr
    if isinstance(evaluator, MetadataEvaluator):
        return _translate_metadata(evaluator)
    # count_tags_expr
    if isinstance(evaluator, CountTagsEvaluator):
        return _translate_count_tags(evaluator)
    # count_members_expr
    # count_distinct_members_expr (CountMembersEvaluator with distinct=True)
    if isinstance(evaluator, CountMembersEvaluator):
        return _translate_count_members(evaluator)
    # count_by_role_expr
    # count_distinct_by_role_expr (CountByRoleEvaluator with distinct=True)
    if isinstance(evaluator, CountByRoleEvaluator):
        return _translate_count_by_role(evaluator)
    # is_closed_expr
    if isinstance(evaluator, IsClosedEvaluator):
        return _translate_is_closed(evaluator)
    # lat_expr
    # lon_expr
    if isinstance(evaluator, CoordinateEvaluator):
        return _translate_coordinate(evaluator)
    # geom_expr: unsupported
    # length_expr
    if isinstance(evaluator, LengthEvaluator):
        return _translate_length(evaluator)
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
        return _translate_conversion(evaluator)
    # suffix_expr
    if isinstance(evaluator, SuffixEvaluator):
        return _translate_suffix(evaluator)
    # abs_expr
    if isinstance(evaluator, AbsEvaluator):
        return _translate_abs(evaluator)
    # is_number_expr
    # is_date_expr
    if isinstance(evaluator, TypeCheckEvaluator):
        return _translate_type_check(evaluator)
    # unique_expr
    if isinstance(evaluator, UniqueEvaluator):
        return _translate_unique(evaluator)
    # min_expr
    # max_expr
    if isinstance(evaluator, MinMaxEvaluator):
        return _translate_minmax(evaluator)
    # sum_expr
    if isinstance(evaluator, SumEvaluator):
        return _translate_sum(evaluator)
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
def _translate_ternary(evaluator: TernaryEvaluator) -> EvaluatorPattern:
    # TODO: translate ternary evaluator
    raise UnimplementedFeatureError(
        "ternary evaluator is not implemented", evaluator.token
    )


# or_expr
# and_expr
def _translate_binary(evaluator: BinaryEvaluator) -> EvaluatorPattern:
    # TODO: translate binary evaluator (||, &&)
    raise UnimplementedFeatureError(
        "binary evaluator is not implemented", evaluator.token
    )


# not_expr
def _translate_unary(evaluator: UnaryEvaluator) -> EvaluatorPattern:
    # TODO: translate unary evaluator (!, -)
    raise UnimplementedFeatureError(
        "unary evaluator is not implemented", evaluator.token
    )


# compare_expr
def _translate_compare(evaluator: CompareEvaluator) -> EvaluatorPattern:
    # TODO: translate compare evaluator (==, !=, <, <=, >, >=)
    raise UnimplementedFeatureError(
        "compare evaluator is not implemented", evaluator.token
    )


# add_expr
def _translate_add(evaluator: AddEvaluator) -> EvaluatorPattern:
    # TODO: translate add evaluator (+, -)
    # Note: + is string concatenation when both operands are strings
    raise UnimplementedFeatureError("add evaluator is not implemented", evaluator.token)


# mul_expr
def _translate_multiply(evaluator: MultiplyEvaluator) -> EvaluatorPattern:
    # TODO: translate multiply evaluator (*, /)
    raise UnimplementedFeatureError(
        "multiply evaluator is not implemented", evaluator.token
    )


# unary_expr (UnaryEvaluator with NEGATE; see _translate_unary)


# literal_expr
def _translate_literal(evaluator: LiteralEvaluator) -> EvaluatorPattern:
    # TODO: translate literal evaluator
    raise UnimplementedFeatureError(
        "literal evaluator is not implemented", evaluator.token
    )


# grouped_expr: no IR class; transformer passes inner evaluator through

# id_expr (MetadataEvaluator; see _translate_metadata)
# type_expr (MetadataEvaluator; see _translate_metadata)


# tag_value_expr
def _translate_tag_value(evaluator: TagValueEvaluator) -> EvaluatorPattern:
    # TODO: translate tag value evaluator (t["key"])
    raise UnimplementedFeatureError(
        "tag value evaluator is not implemented", evaluator.token
    )


# is_tag_expr
def _translate_is_tag(evaluator: IsTagEvaluator) -> EvaluatorPattern:
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
def _translate_metadata(evaluator: MetadataEvaluator) -> EvaluatorPattern:
    # TODO: translate metadata evaluator (id, type, version, timestamp, changeset,
    #   uid, user); dispatch on evaluator.attribute
    raise UnimplementedFeatureError(
        "metadata evaluator is not implemented", evaluator.token
    )


# count_tags_expr
def _translate_count_tags(evaluator: CountTagsEvaluator) -> EvaluatorPattern:
    # TODO: translate count_tags evaluator
    raise UnimplementedFeatureError(
        "count_tags evaluator is not implemented", evaluator.token
    )


# count_members_expr
# count_distinct_members_expr (CountMembersEvaluator with distinct=True)
def _translate_count_members(evaluator: CountMembersEvaluator) -> EvaluatorPattern:
    # TODO: translate count_members evaluator; dispatch on evaluator.distinct
    raise UnimplementedFeatureError(
        "count_members evaluator is not implemented", evaluator.token
    )


# count_by_role_expr
# count_distinct_by_role_expr (CountByRoleEvaluator with distinct=True)
def _translate_count_by_role(evaluator: CountByRoleEvaluator) -> EvaluatorPattern:
    # TODO: translate count_by_role evaluator; dispatch on evaluator.distinct
    raise UnimplementedFeatureError(
        "count_by_role evaluator is not implemented", evaluator.token
    )


# is_closed_expr
def _translate_is_closed(evaluator: IsClosedEvaluator) -> EvaluatorPattern:
    # TODO: translate is_closed evaluator
    raise UnimplementedFeatureError(
        "is_closed evaluator is not implemented", evaluator.token
    )


# lat_expr
# lon_expr
def _translate_coordinate(evaluator: CoordinateEvaluator) -> EvaluatorPattern:
    # TODO: translate coordinate evaluator (lat(), lon())
    # Note: dispatch on evaluator.axis
    raise UnimplementedFeatureError(
        "coordinate evaluator is not implemented", evaluator.token
    )


# geom_expr: unsupported


# length_expr
def _translate_length(evaluator: LengthEvaluator) -> EvaluatorPattern:
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
def _translate_conversion(evaluator: ConversionEvaluator) -> EvaluatorPattern:
    # TODO: translate conversion evaluator (number(), date())
    # Note: dispatch on evaluator.function
    raise UnimplementedFeatureError(
        "conversion evaluator is not implemented", evaluator.token
    )


# suffix_expr
def _translate_suffix(evaluator: SuffixEvaluator) -> EvaluatorPattern:
    # TODO: translate suffix evaluator
    raise UnimplementedFeatureError(
        "suffix evaluator is not implemented", evaluator.token
    )


# abs_expr
def _translate_abs(evaluator: AbsEvaluator) -> EvaluatorPattern:
    # TODO: translate abs evaluator
    raise UnimplementedFeatureError("abs evaluator is not implemented", evaluator.token)


# is_number_expr
# is_date_expr
def _translate_type_check(evaluator: TypeCheckEvaluator) -> EvaluatorPattern:
    # TODO: translate type check evaluator (is_number(), is_date())
    # Note: dispatch on evaluator.function
    raise UnimplementedFeatureError(
        "type check evaluator is not implemented", evaluator.token
    )


# unique_expr
def _translate_unique(evaluator: UniqueEvaluator) -> EvaluatorPattern:
    # TODO: translate unique evaluator
    raise UnimplementedFeatureError(
        "unique evaluator is not implemented", evaluator.token
    )


# min_expr: unsupported
# max_expr: unsupported
def _translate_minmax(evaluator: MinMaxEvaluator) -> EvaluatorPattern:
    # TODO: translate min max evaluator (min(), max())
    # Note: dispatch on evaluator.operator
    raise UnimplementedFeatureError(
        "min max evaluator is not implemented", evaluator.token
    )


# sum_expr
def _translate_sum(evaluator: SumEvaluator) -> EvaluatorPattern:
    # TODO: translate sum evaluator (set_name.sum(evaluator))
    # Note: SumEvaluator is missing operand: Evaluator (the expression to sum over
    #   each element)
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
