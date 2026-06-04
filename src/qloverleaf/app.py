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


def _error_response(message: str, status_code: int = 400) -> Response:
    # Wrap error in the same HTML envelope Overpass uses so clients that parse
    # Overpass error responses (e.g. Overpass Turbo) can display the message.
    html = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"\n'
        '    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">\n'
        "<head>\n"
        '  <meta http-equiv="content-type" content="text/html; charset=utf-8"'
        ' lang="en"/>\n'
        "  <title>Query Error</title>\n"
        "</head>\n"
        "<body>\n"
        '<p><strong style="color:#FF0000">Error</strong>: '
        f"<pre>\n{message}</pre> </p>\n"
        "</body>\n"
        "</html>\n"
    )
    return Response(
        html,
        status_code=status_code,
        media_type="text/html",
        headers={"Access-Control-Allow-Origin": "*"},
    )


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
        return _error_response(str(e))

    query = QueryContext(text=query_text, tree=tree)
    query.stats.parse_time = parse_time

    try:
        content, media_type = await interpreter.initialize(query)
    except Exception as e:
        return _error_response(str(e))
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
