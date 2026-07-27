"""
MaxBodySizeRoute rejects oversized requests by Content-Length, before
FastAPI/python-multipart ever touches the body.

form_finish (app/routers/form_router.py) parses multipart photo uploads.
Resolving its `photos: list[UploadFile] = File(...)` parameter requires
FastAPI to parse the entire multipart body -- spooling parts to disk,
decoding framing -- as part of dependency resolution, before form_finish's
own count and size checks get a chance to run. A client can set
Content-Length to whatever it likes and send far more than any legitimate
submission requires (e.g. 100 files of 50 MB each); the 30/minute rate
limit bounds repetition, not the size of one request.

get_route_handler's wrapper runs before dependency resolution -- the same
seam BodyCapturingRoute (body_capture.py) uses to read the body early --
so raising here skips the multipart parse entirely rather than merely
rejecting after the fact.

Caveat: this is a Content-Length header check, not an enforced body-size
guarantee. A client that omits Content-Length (chunked transfer-encoding)
or lies about it is not caught here. The in-handler count/size checks in
form_finish, which run against actual read bytes, remain the backstop.
"""

from collections.abc import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.core.errors import PAYLOAD_TOO_LARGE
from app.core.upload_constants import MAX_FINISH_REQUEST_BYTES


class MaxBodySizeRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = None
                if declared_size is not None and declared_size > MAX_FINISH_REQUEST_BYTES:
                    raise PAYLOAD_TOO_LARGE(
                        f"Request body exceeds the {MAX_FINISH_REQUEST_BYTES} byte limit"
                    )
            return await original(request)

        return custom_handler
