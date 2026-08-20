"""Application entry point. Holds wiring only, never business logic."""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.constants import Environment
from app.core.docs import DOCS_DISABLED, DOCS_ENABLED, mount_protected_docs
from app.core.exceptions import AppError
from app.core.logging_config import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.core.models import ApiResponse, ErrorPayload
from app.lifespan import lifespan
from app.modules.auth.router import router as auth_router

setup_logging()
log = structlog.get_logger(__name__)

app_configs: dict = {"title": settings.APP_NAME, "lifespan": lifespan}
app_configs.update(DOCS_ENABLED if settings.ENV == Environment.DEV else DOCS_DISABLED)

app = FastAPI(**app_configs)
app.add_middleware(RequestIdMiddleware)

if settings.ENV == Environment.STAGING:
    mount_protected_docs(app)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """Envelope a domain error. code is the i18n key; message is the non-localized default."""
    envelope = ApiResponse[None](
        success=False, error=ErrorPayload(code=exc.code, message=exc.message, context=exc.context)
    )
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump(mode="json", by_alias=True))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Envelope a request body/query validation failure the same way as a domain AppError.

    Without this, FastAPI's own default handler returns {"detail": [...]},
    breaking the one envelope every other endpoint and error already returns
    — see references/api-contract.md. Schema level validators (schemas.py)
    are what raise this, so their errors need the same envelope too.
    """
    envelope = ApiResponse[None](
        success=False,
        error=ErrorPayload(
            code="validation_failed",
            message="Validation failed",
            context={"errors": jsonable_encoder(exc.errors())},
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=envelope.model_dump(mode="json", by_alias=True),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Envelope any error that isn't a domain AppError, without leaking internals."""
    log.exception("unhandled_exception")
    envelope = ApiResponse[None](
        success=False, error=ErrorPayload(code="internal_error", message="Internal server error")
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=envelope.model_dump(mode="json", by_alias=True),
    )


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    """Liveness probe that never touches a dependency."""
    return {"status": "ok"}


app.include_router(auth_router, prefix="/api/v1")
