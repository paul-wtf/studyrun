from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from studyrun.db import make_engine, make_session_factory
from studyrun.deps import get_settings
from studyrun.routes import health


def create_app() -> FastAPI:
    settings = get_settings()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await engine.dispose()

    app = FastAPI(title="studyrun", lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    app.include_router(api)
    return app


app = create_app()
