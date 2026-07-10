from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from protocol_poc.ingest.routes import router as ingest_router
from protocol_poc.config import get_settings
from protocol_poc.guidance.routes import router as guidance_router
from protocol_poc.drafting.routes import router as drafting_router
from protocol_poc.quality.routes import router as quality_router
from protocol_poc.export.routes import router as export_router
from protocol_poc.review.routes import router as review_router
from protocol_poc.db import create_database_engine, create_session_factory


def create_app() -> FastAPI:
    engine = create_database_engine()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="Clinical Protocol POC", version="0.1.0", lifespan=lifespan)
    application.state.engine = engine
    application.state.session_factory = create_session_factory(engine)
    application.include_router(ingest_router)
    application.include_router(guidance_router)
    application.include_router(drafting_router)
    application.include_router(quality_router)
    application.include_router(export_router)
    application.include_router(review_router)
    if get_settings().app_env == "test":
        from protocol_poc.testing.routes import router as testing_router

        application.include_router(testing_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ready", "service": "protocol-poc"}

    return application


app = create_app()
