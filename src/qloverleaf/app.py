from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from qloverleaf.parser import parse


async def listener(request: Request) -> Response:
    if request.method == "POST":
        body = (await request.body()).decode()
        if "&" in body:
            return Response("Unescaped ampersand (&) in query text", status_code=400)
        params = parse_qs(body, separator="&")
        print(params)
        query = params.get("data", [""])[0]
    else:
        query = request.query_params.get("data", "")

    if not query:
        return Response("Missing data parameter", status_code=400)

    # TODO: parse and execute query
    try:
        tree = parse(query)
    except Exception as e:
        return Response(str(e), status_code=400)

    return Response(tree.pretty(), media_type="text/plain")


app = Starlette(routes=[
    Route("/api/interpreter", listener, methods=["GET", "POST"]),
])
