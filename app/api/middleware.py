"""
Request ID middleware — injects a unique request_id into every HTTP request.

The request_id is:
    - Read from the X-Request-ID header if provided by the caller (e.g. API gateway)
    - Generated as a UUID if not provided

It is attached to:
    - The response headers (X-Request-ID)
    - The request.state so it can be accessed by route handlers and agent loops

This enables end-to-end correlation between client requests, agent traces,
and CloudWatch log entries.
"""

from __future__ import annotations

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a unique X-Request-ID into every request/response.

    Usage (registered in main.py):
        app.add_middleware(RequestIDMiddleware)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
