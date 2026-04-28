from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


async def interpreter(request: Request) -> Response:
    if request.method == "POST":
        form = await request.form()
        raw = form.get("data")
        query = str(raw) if raw is not None else ""
    else:
        query = request.query_params.get("data", "")

    if not query:
        return Response("Missing data parameter", status_code=400)

    # TODO: parse and execute query
    return Response("{}", media_type="application/json")


app = Starlette(routes=[
    Route("/api/interpreter", interpreter, methods=["GET", "POST"]),
])
