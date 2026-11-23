from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from studyrun.ai.llm import AnthropicLLM
from studyrun.content.worker import run_worker
from studyrun.db import make_engine, make_session_factory
from studyrun.deps import get_settings
from studyrun.routes import booklets, costs, health, items, modules, runs


def create_app() -> FastAPI:
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = asyncio.Event()
        worker = None
        if settings.worker_enabled:
            worker = asyncio.create_task(
                run_worker(session_factory, AnthropicLLM(settings), stop, settings=settings)
            )
        yield
        stop.set()
        if worker is not None:
            await worker
        await engine.dispose()

    app = FastAPI(title="studyrun", lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(modules.router)
    api.include_router(booklets.router)
    api.include_router(runs.router)
    api.include_router(items.router)
    api.include_router(costs.router)
    app.include_router(api)
    return app


app = create_app()
