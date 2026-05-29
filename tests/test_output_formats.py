from qloverleaf import interpreter
from qloverleaf.parser import parse
from qloverleaf.query_context import QueryContext

# ---------------------------------------------------------------------------
# out debug
# ---------------------------------------------------------------------------


def test_out_debug_one_stmt() -> None:
    import asyncio

    query_text = (
        "[out:raw]; way(381029345) -> .a; node(w.a) -> .b; way(bn.b); out debug;"
    )

    async def run() -> str:
        tree = parse(query_text)
        query = QueryContext(text=query_text, tree=tree)
        content, _media_type = await interpreter.initialize(query)
        chunks = []
        async for chunk in content:
            chunks.append(chunk)
        return "".join(chunks)

    output = asyncio.run(run())
    print(output)
    assert "output_set:" in output
    assert "result_variable:" in output
    assert "distinct:" in output
    assert "materialize:" in output
    assert "prefixes:" in output
    assert "where_clauses:" in output
    assert "injections:" in output
