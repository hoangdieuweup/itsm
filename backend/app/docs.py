"""Docs visibility per environment: open in dev, guarded in staging, off in prod."""

import secrets

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

DOCS_ENABLED = {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
DOCS_DISABLED = {"docs_url": None, "redoc_url": None, "openapi_url": None}

security = HTTPBasic()


def verify_docs_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    """Guard the re-mounted docs routes with HTTP Basic auth in staging."""
    valid_user = secrets.compare_digest(credentials.username, settings.DOCS_USERNAME or "")
    valid_password = secrets.compare_digest(credentials.password, settings.DOCS_PASSWORD or "")
    if not (valid_user and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


def mount_protected_docs(app: FastAPI) -> None:
    """Re-mount the docs routes behind HTTP Basic auth. Call only in staging."""

    @app.get("/openapi.json", include_in_schema=False)
    async def protected_openapi(_: None = Depends(verify_docs_credentials)) -> dict:
        """Serve the OpenAPI schema behind HTTP Basic auth."""
        return get_openapi(title=app.title, version=app.version, routes=app.routes)

    @app.get("/docs", include_in_schema=False)
    async def protected_swagger_ui(_: None = Depends(verify_docs_credentials)):
        """Serve Swagger UI behind HTTP Basic auth."""
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")

    @app.get("/redoc", include_in_schema=False)
    async def protected_redoc(_: None = Depends(verify_docs_credentials)):
        """Serve ReDoc behind HTTP Basic auth."""
        return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")
