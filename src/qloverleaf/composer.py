from __future__ import annotations

import re
from typing import TYPE_CHECKING

# TODO: consider refactoring to avoid circular imports
if TYPE_CHECKING:
    from qloverleaf.interpreter import SetState

from qloverleaf.transformer import _AREA, _NWR
from qloverleaf.translator import SparqlPattern


def _substitute_variable(clause: str, old_var: str, new_var: str) -> str:
    """
    Replace all occurrences of old_var with new_var in a SPARQL clause.

    Only matches complete variable names, not substrings. For example,
    replacing "?x" won't affect "?x_foo" or "?x·geom".

    Args:
        clause: SPARQL clause containing variables
        old_var: Variable to replace (e.g., "?craters1")
        new_var: Replacement variable (e.g., "?_1")

    Returns:
        Clause with variable substituted
    """
    # Escape special regex characters in the variable name (handles ? and ·)
    escaped_old = re.escape(old_var)

    # Match variable only when NOT followed by characters that can be part of a variable
    # name. SPARQL variables in this codebase can contain: letters, digits, _, ·
    pattern = escaped_old + r"(?![a-zA-Z0-9_·])"

    return re.sub(pattern, new_var, clause)


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

    # A single SPARQL query cannot produce both NWR and AREA results — the caller
    # must handle this via local execution instead. See area-handling.md.
    if pattern.output_set:
        content_types = pattern.output_set.content_types
        assert content_types is not None
        if content_types & _NWR and content_types & _AREA:
            return None

    # Start with current pattern's where clauses
    composed_where_clauses = list(pattern.where_clauses)
    composed_prefixes = set(pattern.prefixes)
    composed_distinct = pattern.distinct
    remaining_injections = []

    # Try to inline each injection
    for injection in pattern.injections:
        # Skip if must materialize
        if injection.must_materialize:
            remaining_injections.append(injection)
            continue

        # Get input set state
        input_set = set_state.get(injection.set_name)
        assert input_set
        if input_set.nwr_results or input_set.area_results:
            # set is already materialized
            remaining_injections.append(injection)
            continue

        # Input pattern is cold - inline it
        input_pattern = input_set.pattern
        assert input_pattern

        # Cold patterns should not have SELECT clauses
        assert not input_pattern.select_clause

        # Cold patterns should not have GROUP BY clauses
        assert not input_pattern.group_by

        # Cold patterns should not have ORDER BY clauses
        assert not input_pattern.order_by

        # Cold patterns should not have LIMIT clauses
        assert not input_pattern.limit

        # Substitute: replace input_pattern.result_variable with injection.sparql_var
        input_result_variable = input_pattern.result_variable
        assert input_result_variable is not None
        substituted_clauses = [
            _substitute_variable(clause, input_result_variable, injection.sparql_var)
            for clause in input_pattern.where_clauses
        ]

        # merge prefixes
        composed_prefixes = composed_prefixes | input_pattern.prefixes

        # carry distinct forward
        composed_distinct = composed_distinct | input_pattern.distinct

        if injection.marker is not None:
            # Site injection: substitute the marker inside the existing where_clause
            # string rather than appending to the flat clause list
            cold_block = "\n  ".join(substituted_clauses)
            for i, clause in enumerate(composed_where_clauses):
                if injection.marker in clause:
                    composed_where_clauses[i] = clause.replace(
                        injection.marker, cold_block
                    )
                    break
        else:
            # Flat injection: append substituted clauses and deduplicate
            composed_where_clauses.extend(substituted_clauses)
            composed_where_clauses = list(dict.fromkeys(composed_where_clauses))

        # Reduce: don't add this injection to remaining_injections (it's been inlined)
        continue

    composed_pattern = SparqlPattern(
        pattern.output_set,
        pattern.materialize,  # false
        pattern.output,
        composed_prefixes,
        pattern.select_clause,  # None
        composed_distinct,
        pattern.group_by,
        pattern.order_by,
        composed_where_clauses,
        remaining_injections,
        pattern.limit,
    )

    return composed_pattern
