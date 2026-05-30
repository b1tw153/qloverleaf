import time
from collections.abc import AsyncGenerator
from importlib.resources import files
from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from qloverleaf import interpreter
from qloverleaf.parser import parse
from qloverleaf.query_context import QueryContext


async def _safe_stream(
    generator: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    try:
        async for chunk in generator:
            yield chunk
    except Exception as e:
        yield f"\n\n[ERROR: {e}]"


async def health(request: Request) -> Response:
    return Response("ok")


async def listener(request: Request) -> Response:
    if request.method == "POST":
        body = (await request.body()).decode()
        if "&" in body:
            return Response("Unescaped ampersand (&) in query text", status_code=400)
        params = parse_qs(body, separator="&")
        print(params)
        query_text = params.get("data", [""])[0]
    else:
        raw_query = request.url.query
        if "&" in raw_query:
            return Response("Unescaped ampersand (&) in query text", status_code=400)
        query_text = request.query_params.get("data", "")

    if not query_text:
        return Response("Missing data parameter", status_code=400)

    try:
        start_time = time.perf_counter()
        tree = parse(query_text)
        parse_time = time.perf_counter() - start_time
    except Exception as e:
        return Response(str(e), status_code=400)

    query = QueryContext(text=query_text, tree=tree)
    query.stats.parse_time = parse_time

    try:
        content, media_type = await interpreter.initialize(query)
    except Exception as e:
        return Response(str(e), status_code=400)
    return StreamingResponse(
        _safe_stream(content),
        media_type=media_type,
        headers={"Access-Control-Allow-Origin": "*"},
    )


_static_path = str(files("qloverleaf").joinpath("static"))

app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/api/interpreter", listener, methods=["GET", "POST"]),
        Mount("/", StaticFiles(directory=_static_path, html=True)),
    ]
)
