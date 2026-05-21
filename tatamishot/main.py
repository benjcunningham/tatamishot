import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette_context import context
from starlette_context.middleware import RawContextMiddleware
from starlette_context.plugins import CorrelationIdPlugin, RequestIdPlugin

from tatamishot.config import settings
from tatamishot.log import configure_logging
from tatamishot.routes import router


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from starlette.responses import Response

configure_logging()


class LogContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[..., Response]) -> Response:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=context.get("X-Request-ID"),
            correlation_id=context.get("X-Correlation-ID"),
        )
        return await call_next(request)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    os.makedirs(settings.output_dir, exist_ok=True)
    yield


app = FastAPI(title="TatamiShot", lifespan=lifespan)
app.add_middleware(LogContextMiddleware)
app.add_middleware(RawContextMiddleware, plugins=[RequestIdPlugin(), CorrelationIdPlugin()])
app.include_router(router)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
