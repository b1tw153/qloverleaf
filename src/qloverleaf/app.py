import time
from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from qloverleaf import interpreter
from qloverleaf.parser import parse
from qloverleaf.query import Query


async def listener(request: Request) -> Response:
    if request.method == "POST":
        body = (await request.body()).decode()
        if "&" in body:
            return Response("Unescaped ampersand (&) in query text", status_code=400)
        params = parse_qs(body, separator="&")
        print(params)
        query_text = params.get("data", [""])[0]
    else:
        query_text = request.query_params.get("data", "")

    if not query_text:
        return Response("Missing data parameter", status_code=400)


    try:
        start_time = time.perf_counter()
        tree = parse(query_text)
        parse_time = time.perf_counter() - start_time
    except Exception as e:
        return Response(str(e), status_code=400)

    query = Query(text=query_text, tree=tree)
    query.stats.parse_time = parse_time

    media_type, generator = await interpreter.initialize(query)
    return StreamingResponse(generator, media_type=media_type)


app = Starlette(routes=[
    Route("/api/interpreter", listener, methods=["GET", "POST"]),
])
