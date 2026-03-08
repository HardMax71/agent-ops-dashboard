from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentops.api.routers.auth import router as auth_router
from agentops.api.routers.internal import router as internal_router
from agentops.api.routers.jobs import router as jobs_router
from agentops.auth.middleware import SecurityHeadersMiddleware
from agentops.config import get_settings
from agentops.lifespan import lifespan


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AgentOps Dashboard API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware, frontend_origin=settings.frontend_origin)

    app.include_router(jobs_router)
    app.include_router(auth_router)
    app.include_router(internal_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
