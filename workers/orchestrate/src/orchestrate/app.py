from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from piratepod_core import make_app

from .config import ORCHESTRATE_POLL_INTERVAL, ORCHESTRATE_SQLITE_PATH
from .db import JobRepo
from .routes import router
from .service import run_pipeline
from .worker import JobWorker


@asynccontextmanager
async def lifespan(app) -> AsyncIterator[None]:
    repo = JobRepo(ORCHESTRATE_SQLITE_PATH)
    repo.init()
    worker = JobWorker(repo, run_pipeline, ORCHESTRATE_POLL_INTERVAL)
    app.state.repo = repo
    app.state.worker = worker
    worker.start()
    try:
        yield
    finally:
        await worker.stop()


app = make_app("piratepod-orchestrate", lifespan=lifespan)
app.include_router(router)
