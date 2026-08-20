"""Templates for the application root, which holds mechanism only."""


def docs() -> str:
    """Render app/docs.py: the docs_url matrix and the staging auth guard.

    Lives apart from main.py so main.py stays wiring only — registering routes
    and checking credentials is a mechanism concern, not app assembly.
    """
    return '''
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
'''


def main(modules: list[str]) -> str:
    """Render app/main.py: wiring only, never business logic."""
    imports = "\n".join(f"from app.modules.{m}.router import router as {m}_router" for m in modules)
    includes = "\n".join(f'app.include_router({m}_router, prefix="/api/v1")' for m in modules)
    return f'''
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
from app.lifespan import lifespan
from app.core.logging_config import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.core.models import ApiResponse, ErrorPayload
{imports}

setup_logging()
log = structlog.get_logger(__name__)

app_configs: dict = {{"title": settings.APP_NAME, "lifespan": lifespan}}
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

    Without this, FastAPI's own default handler returns {{"detail": [...]}},
    breaking the one envelope every other endpoint and error already returns
    — see references/api-contract.md. Schema level validators (schemas.py)
    are what raise this, so their errors need the same envelope too.
    """
    envelope = ApiResponse[None](
        success=False,
        error=ErrorPayload(
            code="validation_failed",
            message="Validation failed",
            context={{"errors": jsonable_encoder(exc.errors())}},
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
    return {{"status": "ok"}}


{includes}
'''


def constants() -> str:
    """Render app/constants.py holding only project wide enums."""
    return '''
"""Project wide constants. Business constants belong to their own module."""

from enum import StrEnum


class Environment(StrEnum):
    """Deployment environment the process is running in."""

    DEV = "dev"
    STAGING = "stg"
    PRODUCTION = "prod"

    @property
    def is_debug(self) -> bool:
        """Return whether debug level logging is enabled in this environment."""
        return self is self.DEV


class LogLevel(StrEnum):
    """Valid values for LOG_LEVEL. A closed set, not a free string."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
'''


def config(name: str) -> str:
    """Render app/config.py holding only settings shared by the whole process."""
    return f'''
"""Global settings. Module specific settings live in that module's config.py."""

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import Environment, LogLevel


class Config(BaseSettings):
    """Settings that genuinely belong to the whole process."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "{name}"
    ENV: Environment = Environment.PRODUCTION
    LOG_LEVEL: LogLevel = LogLevel.INFO

    DATABASE_URL: PostgresDsn
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_STATEMENT_TIMEOUT_MS: int = 30000

    CORS_ORIGINS: list[str] = []

    DOCS_USERNAME: str | None = None
    DOCS_PASSWORD: str | None = None


settings = Config()
'''


def exceptions() -> str:
    """Render app/exceptions.py holding the error mechanism, not the catalogue."""
    return '''
"""Error mechanism shared by every module.

Concrete errors such as UserNotFound belong to the module that owns the concept.
Only the base classes and the HTTP mapping live here.
"""

from typing import Any


class AppError(Exception):
    """Base error carrying a stable machine readable code and optional context."""

    code = "app_error"
    status_code = 400
    message = "Application error"

    def __init__(self, message: str | None = None, **context: Any) -> None:
        self.message = message or self.message
        self.context = context
        super().__init__(self.message)


class NotFoundError(AppError):
    """Base for every missing resource error."""

    code = "not_found"
    status_code = 404
    message = "Resource not found"


class ConflictError(AppError):
    """Base for every uniqueness or state conflict."""

    code = "conflict"
    status_code = 409
    message = "Conflicting state"


class ForbiddenError(AppError):
    """Base for every permission failure."""

    code = "forbidden"
    status_code = 403
    message = "Not permitted"


class ValidationFailedError(AppError):
    """Base for input that is well formed but violates a business rule."""

    code = "validation_failed"
    status_code = 422
    message = "Validation failed"


class IntegrationError(AppError):
    """Base for failures originating in an external system."""

    code = "integration_error"
    status_code = 502
    message = "Upstream integration failed"
'''


def models() -> str:
    """Render app/models.py holding the shared Pydantic base and the response envelope."""
    return '''
"""Base Pydantic models applied across the whole application.

Every model here serializes to camelCase on the wire while Python code stays
snake_case — see references/api-contract.md for the full wire contract:
camelCase, the ApiResponse envelope, and the error code / i18n convention.
"""

from datetime import datetime
from typing import Any, Generic, TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CustomModel(BaseModel):
    """Base model enforcing camelCase on the wire and one datetime format."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _serialize_datetimes(self, value: Any) -> Any:
        """Emit every datetime in UTC with an explicit offset."""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=ZoneInfo("UTC"))
            return value.strftime("%Y-%m-%dT%H:%M:%S%z")
        return value


class FrozenModel(CustomModel):
    """Immutable base for values that cross layers or a cache boundary."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True, frozen=True
    )


class ErrorPayload(FrozenModel):
    """The error half of ApiResponse.

    code is a stable, non-localized key — the frontend maps it to a
    translated string via its own i18n system when one is present. message
    is an English default for logs and API consumers with no i18n layer;
    never render it directly to an end user once i18n exists.
    """

    code: str
    message: str
    context: dict[str, Any] = {}


class ApiResponse(FrozenModel, Generic[T]):
    """The one response envelope every endpoint returns, over REST or SSE alike."""

    success: bool
    data: T | None = None
    error: ErrorPayload | None = None
'''


def database() -> str:
    """Render app/database.py holding connection concerns only."""
    return '''
"""Database connection, declarative base and naming conventions."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    """Declarative base with explicit index and constraint naming."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request scoped session, committing on success and rolling back on failure.

    This is the transaction boundary for any module using `--minimal` (no
    uow.py): a repository only ever calls flush(), never commit() — see
    references/architecture.md#transactions — so something has to commit
    once the request finishes cleanly. For a module WITH a unit of work,
    uow.commit() already ran before the route handler returned; committing
    an already-committed, empty transaction here is a harmless no-op, not a
    double write.
    """
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
'''


def pagination() -> str:
    """Render app/pagination.py as a global mechanism module."""
    return '''
"""Pagination primitives shared by every list endpoint."""

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

from app.core.models import CustomModel

T = TypeVar("T")


class PaginationDefaults:
    """Bounds every paginated endpoint agrees to."""

    MAX_PAGE_SIZE = 200
    DEFAULT_PAGE_SIZE = 50


class PaginationParams(BaseModel):
    """Query parameters accepted by every paginated endpoint. Not a response body — no camelCase concern."""

    limit: int = PaginationDefaults.DEFAULT_PAGE_SIZE
    offset: int = 0


class Page(CustomModel, Generic[T]):
    """One page of results together with the total count."""

    items: list[T]
    total: int
    limit: int
    offset: int


async def pagination_params(
    limit: int = Query(PaginationDefaults.DEFAULT_PAGE_SIZE, ge=1, le=PaginationDefaults.MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> PaginationParams:
    """Provide validated pagination parameters to a route."""
    return PaginationParams(limit=limit, offset=offset)
'''


def events() -> str:
    """Render app/events.py holding the event mechanism only."""
    return '''
"""Event mechanism. Concrete events belong to the module that publishes them."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DomainEvent(BaseModel):
    """Base class carrying the identity every consumer needs to deduplicate."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event to a broker."""
        raise NotImplementedError


Handler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """Dispatches events in process to handlers registered by type."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> None:
        """Register one handler for one event type."""
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Deliver an event without letting a handler failure reach the caller."""
        handlers = self._handlers.get(type(event), [])
        results = await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.exception("event handler failed event=%s", type(event).__name__)


event_bus = EventBus()


async def get_event_bus() -> EventBus:
    """Provide the shared event bus."""
    return event_bus
'''


def logging_config(with_tracing: bool) -> str:
    """Render app/logging_config.py.

    structlog is configured with a stdlib logger_factory, and the stdlib root
    logger is given a ProcessorFormatter built from the same processor chain.
    That means every `logging.getLogger(__name__)` call already scattered
    through the integration and domain templates emits the same JSON shape as
    native structlog calls, with no changes needed at each call site.
    """
    if with_tracing:
        trace_import = "\nfrom opentelemetry import trace\n"
        trace_processor = "\n    _add_trace_context,"
        trace_function = '''

def _add_trace_context(logger, method_name, event_dict):
    """Attach the active span's trace_id and span_id, when one exists."""
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict
'''
    else:
        trace_import = ""
        trace_processor = ""
        trace_function = ""

    return f'''
"""Structured logging.

One JSON shape whether a log line comes from structlog or the standard
library, with request context (and trace context, when tracing is enabled)
merged in automatically instead of passed by hand at every call site.
"""

import logging
import sys

import structlog
{trace_import}
from app.config import settings
from app.constants import LogLevel

SENSITIVE_KEYS = {{"password", "token", "authorization", "secret", "api_key", "credit_card"}}


def _redact_sensitive(logger, method_name, event_dict):
    """Mask values behind keys that should never reach a log sink."""
    for key in event_dict:
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict
{trace_function}

SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,{trace_processor}
    _redact_sensitive,
]


def setup_logging() -> None:
    """Route structlog and stdlib logging through one formatter and level."""
    structlog.configure(
        processors=[*SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.dev.ConsoleRenderer(colors=True)
        if settings.ENV.is_debug
        else structlog.processors.JSONRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=SHARED_PROCESSORS,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(LogLevel.DEBUG if settings.ENV.is_debug else settings.LOG_LEVEL)
'''


def middleware() -> str:
    """Render app/middleware.py holding ASGI middleware applied to every request."""
    return '''
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
'''


def worker(modules: list[str], with_cache: bool) -> str:
    """Render app/worker.py: the consumer process entry point, run by scripts/start-worker.sh.

    Only generated when the queue integration is selected. A separate process
    from the API on purpose — see integrations/queue/client.py's module
    docstring and references/messaging.md's "Consumer process" section.
    """
    exchanges = ", ".join(f'"{m}"' for m in modules) or '"app"'

    if with_cache:
        idempotency_import = (
            "\nfrom app.integrations.cache.client import RedisConnectionFactory\n"
            "from app.integrations.queue.idempotency import RedisIdempotencyStore, idempotent"
        )
        handler_setup = '''    redis = RedisConnectionFactory.create()
    handler = idempotent(RedisIdempotencyStore(redis))(handle_message)
'''
        handler_ref = "handler"
        redis_close = "    await redis.aclose()\n"
    else:
        idempotency_import = ""
        handler_setup = (
            "    # cache not selected — handle_message runs unwrapped. Add `cache` and wrap it with\n"
            "    # `idempotent(RedisIdempotencyStore(...))` (integrations/queue/idempotency.py) once\n"
            "    # redelivery needs deduplicating; see references/messaging.md#idempotent-consumers.\n"
            "    handler = handle_message\n"
        )
        handler_ref = "handler"
        redis_close = ""

    return f'''
"""Consumer process entry point. Runs separately from the API — see scripts/start-worker.sh.

Owns nothing the API doesn't already own: same settings, same use cases. A
slow or crashing consumer must never be able to starve request handling in
the API process, which is why this is its own process, not a background task
bolted onto app/main.py.
"""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable

from app.integrations.queue.client import Broker
from app.core.logging_config import setup_logging
{idempotency_import}

setup_logging()
logger = logging.getLogger(__name__)

QUEUE_PREFIX = "app.work"
EXCHANGES = [{exchanges}]


async def handle_message(body: bytes) -> None:
    """Route one message to the use case that owns it.

    Placeholder — dispatch on a type field in the message body to whichever
    module should react to it. Keep this a dispatch table, not a growing
    if/elif chain: {{"identity.created": handle_identity_created, ...}}.
    """
    logger.info("message received bytes=%s", len(body))


async def consume_one(broker: Broker, exchange: str, handler: Callable[[bytes], Awaitable[None]]) -> None:
    """Consume everything published on one module's exchange."""
    await broker.consume(f"{{QUEUE_PREFIX}}.{{exchange}}", exchange, ["#"], handler)


async def main() -> None:
    """Connect, consume every module's exchange until stopped, then close cleanly."""
    broker = Broker()
    await broker.connect()

{handler_setup}
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    tasks = [asyncio.create_task(consume_one(broker, exchange, {handler_ref})) for exchange in EXCHANGES]
    logger.info("worker started exchanges=%s", EXCHANGES)

    await stop.wait()
    logger.info("worker stopping")
    for task in tasks:
        task.cancel()
    await broker.close()
{redis_close}

if __name__ == "__main__":
    asyncio.run(main())
'''


def repository() -> str:
    """Render app/repository.py: the abstract repository contract.

    Root mechanism only — the Repository pattern from Percival & Gregory's
    "Architecture Patterns with Python" (cosmicpython.com). A service depends
    on this abstraction, never on a module's concrete SQLAlchemy class, so
    storage can be swapped or faked in a unit test without touching a use
    case. See references/layer-examples.md for the full worked example.
    """
    return '''
"""Abstract repository contract every module's concrete repository implements."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

EntityT = TypeVar("EntityT")


class AbstractRepository(ABC, Generic[EntityT]):
    """The read contract every module's repository must satisfy.

    Each module extends this with its own write and lookup methods — see
    references/layer-examples.md.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: int) -> EntityT | None:
        """Return one entity, or None when it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_page(self, limit: int, offset: int) -> tuple[list[EntityT], int]:
        """Return one page of entities together with the total count."""
        raise NotImplementedError
'''


def unit_of_work() -> str:
    """Render app/uow.py: the abstract transaction-boundary contract."""
    return '''
"""Abstract unit-of-work contract every module's concrete UoW implements."""

from abc import ABC, abstractmethod


class AbstractUnitOfWork(ABC):
    """Async context manager owning one transaction boundary.

    __aexit__ rolls back automatically on any exception, so a concrete
    subclass only ever has to implement commit() and rollback().
    """

    async def __aenter__(self) -> "AbstractUnitOfWork":
        """Enter the transactional scope."""
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Roll back whenever the block raised."""
        if exc_type is not None:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None:
        """Commit the transaction, applying any deferred side effect only on success."""
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Roll back the transaction, undoing any deferred side effect too."""
        raise NotImplementedError
'''


def use_case() -> str:
    """Render app/use_case.py: the abstract contract behind rule #9."""
    return '''
"""Abstract use-case contract every module's service class implements.

Makes rule #9 (one use case, one class, one execute()) structural instead of
only documented: a concrete class that forgets execute() cannot be
instantiated — Python raises TypeError at the call site, not a linter
warning at review time. Input and output are left to each concrete class to
type: a Get use case, a List use case and a Create use case take genuinely
different arguments, so forcing one shared signature here would fight the
domain instead of describing it.
"""

from abc import ABC, abstractmethod
from typing import Any


class AbstractUseCase(ABC):
    """One orchestration step: validate, call the repository or uow, publish."""

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Run the use case and return its result."""
        raise NotImplementedError
'''


def markers() -> str:
    """Render app/markers.py: decorator classes tagging a method with its architectural role.

    Purely informational — no behavior change, nothing here is checked by
    lint-imports or ruff. A class like a repository has main operations and
    auxiliary/private ones (get_by_id vs _load_by_id); the marker belongs on
    the method that has a role, not blanket-applied to the whole class.
    """
    return '''
"""Layer markers: decorator classes that tag a method with its architectural role.

Implemented as classes, not functions returning closures, so each marker is a
named, reusable unit like every other role in this codebase — lowercase by
design, read as an annotation the same way @property/@staticmethod already are.

Fully transparent: __get__ delegates to the wrapped function's own descriptor
protocol, so a decorated method binds self and awaits exactly as if this
decorator were never applied — verified for sync, async, and @staticmethod.

The overloaded __new__ makes these markers invisible to the type checker: the
first overload says "marker(func) returns the same callable type it received",
so a @integration-decorated method still satisfies a Protocol that declares the
same method as a plain async def. Without this, the type checker sees a
_MethodMarker descriptor — a different kind of attribute — and rejects
structural subtyping with "must both be descriptors".

See references/layer-examples.md for which method in each module gets which
marker. A method carrying more than one marker is a sign it is doing more
than one job — split it instead of stacking markers.
"""

import functools
from collections.abc import Callable
from typing import Any, TypeVar, overload

_F = TypeVar("_F", bound=Callable[..., Any])


class _MethodMarker:
    """Base for every marker below. Never used directly."""

    layer: str

    @overload
    def __new__(cls, func: _F) -> _F: ...  # type: ignore[misc]
    @overload
    def __new__(cls, func: Callable[..., Any]) -> "_MethodMarker": ...
    def __new__(cls, func: Callable[..., Any]) -> Any:
        instance = super().__new__(cls)
        instance._init(func)
        return instance

    def _init(self, func: Callable[..., Any]) -> None:
        functools.update_wrapper(self, func)
        self._func = func
        setattr(func, "__layer__", self.layer)  # noqa: B010 -- dynamic attribute, not a fixed attr of Callable

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        """Delegate binding to the wrapped function — sync and async both bind correctly this way."""
        if obj is None:
            return self._func
        return self._func.__get__(obj, objtype)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Forward straight through for a bare function (no class involved)."""
        return self._func(*args, **kwargs)


class database(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method that reads or writes a module's own tables directly."""

    layer = "database"


class helper(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method with no business decision: formatting, normalization, or support for another method."""

    layer = "helper"


class rule(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method holding a pure business decision — no I/O."""

    layer = "rule"


class use_case(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """The execute() of a use case — one class, one operation."""

    layer = "use_case"


class facade(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method exposed to other modules through public.py."""

    layer = "facade"


class integration(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method that calls an external system directly (Redis, RabbitMQ, object storage)."""

    layer = "integration"
'''


def retry() -> str:
    """Render app/retry.py: a backoff decorator for transient failures in external calls.

    Root mechanism, not an integration — every integration's client can use
    it, it depends on none of them. Not a substitute for the queue's own
    retry-via-DLX (references/messaging.md), which handles a message failing
    after every in-process attempt here is already exhausted.
    """
    return '''
"""Retry decorator for transient failures in external calls.

Reach for this on a call to an external system (storage, an HTTP client to
another service) that can fail transiently. It is not a substitute for the
queue's own retry-via-DLX — that handles a message still failing after every
attempt here is exhausted; see references/messaging.md.
"""

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

R = TypeVar("R")


class retry:  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """Retry an async call with exponential backoff on the given exception types.

    Raises the last exception once attempts is exhausted — this only absorbs
    the transient case, the caller still decides what "still failing" means.
    """

    def __init__(
        self,
        *,
        attempts: int = 3,
        base_delay_seconds: float = 0.5,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self._attempts = attempts
        self._base_delay_seconds = base_delay_seconds
        self._exceptions = exceptions

    def __call__(self, func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @functools.wraps(func)
        async def wrapped(*args: Any, **kwargs: Any) -> R:
            delay = self._base_delay_seconds
            for attempt in range(1, self._attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except self._exceptions as exc:
                    if attempt == self._attempts:
                        raise
                    logger.warning(
                        "retrying %s after attempt %s/%s: %s", func.__name__, attempt, self._attempts, exc
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
            raise AssertionError("unreachable")  # loop above always returns or raises

        return wrapped
'''


def lifespan(integrations: list[str]) -> str:
    """Render app/lifespan.py creating every pool owned by the process."""
    imports, startup, shutdown = [], [], []

    if "tracing" in integrations:
        imports.append("from app.integrations.tracing.client import setup_tracing, shutdown_tracing")
        startup.append("    app.state.tracer_provider = setup_tracing(app, settings.APP_NAME, settings.ENV.value)")
        shutdown.append("    shutdown_tracing(app.state.tracer_provider)")

    if "cache" in integrations:
        imports.append("from app.integrations.cache.client import RedisConnectionFactory")
        startup.append("    app.state.redis = RedisConnectionFactory.create()")
        shutdown.append("    await app.state.redis.aclose()")

    if "queue" in integrations:
        imports.append("from app.integrations.queue.client import Broker")
        startup.append("    app.state.broker = Broker()\n    await app.state.broker.connect()")
        shutdown.append("    await app.state.broker.close()")

    if "storage" in integrations:
        imports.append("from app.integrations.storage.client import StorageClient")
        startup.append("    app.state.storage = StorageClient()")
        shutdown.append("    await app.state.storage.close()")

    import_block = "\n".join(imports)
    startup_block = "\n".join(startup)
    shutdown_block = "\n".join(shutdown)

    return f'''
"""Ownership of every shared resource, bound to the application lifecycle."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
{import_block}

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create pools on startup and release them on shutdown."""
    engine = create_async_engine(
        str(settings.DATABASE_URL),
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        connect_args={{
            "server_settings": {{"statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS)}}
        }},
    )
    app.state.engine = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
{startup_block}

    logger.info("application resources initialized")
    yield

{shutdown_block}
    await engine.dispose()
    logger.info("application resources released")
'''
