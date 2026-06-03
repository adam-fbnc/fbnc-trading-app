"""
Request observability: a middleware that logs every request with timing and
status, plus a global exception handler that logs full tracebacks for any
unhandled error (so 500s always leave a complete stack trace in the logs).
"""
import logging
import time
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id
        start = time.perf_counter()

        logger.info("--> [%s] %s %s", request_id, request.method, request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                "ERR [%s] %s %s unhandled error after %.1fms\n%s",
                request_id, request.method, request.url.path, elapsed,
                traceback.format_exc(),
            )
            raise

        elapsed = (time.perf_counter() - start) * 1000
        log = logger.warning if response.status_code >= 500 else (
            logger.info if response.status_code < 400 else logger.warning
        )
        log("<-- [%s] %s %s %d (%.1fms)",
            request_id, request.method, request.url.path, response.status_code, elapsed)
        response.headers["X-Request-ID"] = request_id
        return response


def register_observability(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "????????")
        logger.error(
            "Unhandled exception [%s] on %s %s:\n%s",
            request_id, request.method, request.url.path,
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal Server Error",
                "request_id": request_id,
                "error_type": type(exc).__name__,
            },
        )
