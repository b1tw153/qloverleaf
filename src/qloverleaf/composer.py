"""Pattern composition for cold set inlining."""

from __future__ import annotations

from qloverleaf.interpreter import SetState
from qloverleaf.translator import SparqlPattern


def compose(pattern: SparqlPattern, set_state: SetState) -> SparqlPattern | None:
    """
    Attempt to compose pattern with its input sets.

    Applies the substitute-concatenate-deduplicate-reduce algorithm to inline
    cold input patterns into the current pattern, eliminating unnecessary
    materialization.

    Args:
        pattern: The pattern to compose
        set_state: Maps set names to:
          {
            "pattern": SparqlPattern | None,
            "results": list | None
          }

    Returns:
        Composed pattern if successful, None if composition is not possible
    """
    # Fast-path: pattern is statically hot, must execute
    if pattern.materialize:
        return None

    # Fast-path: if all injections must materialize, composition not possible
    if pattern.injections and all(inj.must_materialize for inj in pattern.injections):
        return None

    # Start with current pattern's where clauses
    composed_where_clauses = list(pattern.where_clauses)
    remaining_injections = []

    # Try to inline each injection
    for injection in pattern.injections:
        # Skip if must materialize
        if injection.must_materialize:
            remaining_injections.append(injection)
            continue

        # Get input set state
        input_set = set_state.get(injection.set_name)
        if not input_set or input_set.pattern is None:
            # Input not available or already materialized - keep injection
            remaining_injections.append(injection)
            continue

        # Input pattern is cold - inline it
        input_pattern = input_set.pattern

        # Substitute: replace input_pattern.result_variable with injection.sparql_var
        substituted_clauses = [
            clause.replace(input_pattern.result_variable, injection.sparql_var)
            for clause in input_pattern.where_clauses
        ]

        # Concatenate: append substituted clauses
        composed_where_clauses.extend(substituted_clauses)

        # Reduce: don't add this injection to remaining_injections (it's been inlined)

    return None
