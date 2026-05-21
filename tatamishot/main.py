import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tatamishot.config import settings
from tatamishot.log import configure_logging
from tatamishot.routes import router


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    os.makedirs(settings.output_dir, exist_ok=True)
    yield


app = FastAPI(title="TatamiShot", lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
