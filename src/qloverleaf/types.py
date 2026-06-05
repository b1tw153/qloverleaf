from dataclasses import dataclass, field

from qloverleaf.transformer import ElementType, SetReference, Statement


@dataclass
class SetInjection:
    sparql_var: str  # e.g. "?a0"
    set_name: str  # versioned set name to look up in set state, e.g. "a0"
    # required_types specifies what the injection consumes from the set;
    # None means whatever the set contains
    required_types: frozenset[ElementType] | None
    must_materialize: bool = (
        False  # True if this input must be materialized (cannot compose)
    )
    # marker: if set, substitute this placeholder string in where_clauses with
    # VALUES {sparql_var} { uri_list } (hot) or cold clauses (cold), rather
    # than emitting a top-level VALUES block
    marker: str | None = None


@dataclass
class SparqlPattern:
    output_set: SetReference | None
    materialize: bool = False
    prefixes: set[str] = field(default_factory=set)
    select_clause: str | None = None
    group_by: str | None = None
    order_by: str | None = None
    where_clauses: list[str] = field(default_factory=list)
    injections: list[SetInjection] = field(default_factory=list)
    limit: int | None = None
    statements: list[Statement] = field(default_factory=list)

    @property
    def result_variable(self) -> str | None:
        """SPARQL variable name with ? prefix (e.g., '?craters1')"""
        return f"?{self.output_set.identifier}" if self.output_set else None

    @property
    def result_set_name(self) -> str | None:
        """Set state key without ? prefix (e.g., 'craters1')"""
        return self.output_set.identifier if self.output_set else None


@dataclass
class SetStateEntry:
    pattern: SparqlPattern | None
    nwr_results: list[tuple[ElementType, str]] | None
    area_results: list[tuple[ElementType, str]] | None


SetState = dict[str, SetStateEntry]
