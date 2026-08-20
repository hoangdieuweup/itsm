"""ASGI middleware. Applies to every request, so it stays mechanism only."""

import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind request_id and correlation_id to every log emitted while handling a request.

    request_id identifies this request in this service — reused only if the
    caller is retrying the exact same request via X-Request-ID, otherwise
    generated fresh per hop. correlation_id identifies the whole distributed
    flow: read from X-Correlation-ID when a caller propagated one, otherwise
    this hop is where the flow starts and correlation_id equals request_id.
    See references/logging.md for the full convention, including how this
    pair propagates through the queue integration.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Bind both ids to context, then echo them back on the response."""
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        correlation_id = request.headers.get("x-correlation-id") or request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response
