import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.logging_config import request_id_var

logger = logging.getLogger(__name__)


def get_request_id(request: Request):
    return request_id_var.get()


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request data",
            },
            "request_id": get_request_id(request),
        },
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    return JSONResponse(
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
            },
            "request_id": get_request_id(request),
        },
    )


async def general_exception_handler(
    request: Request,
    exc: Exception,
):
    request_id = getattr(request.state, "request_id", None)

    token = request_id_var.set(request_id)

    try:
        logger.error(
            "Unhandled application error: %s",
            type(exc).__name__,
        )
    finally:
        request_id_var.reset(token)

    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": request_id} if request_id else {},
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
            },
            "request_id": request_id,
        },
    )
