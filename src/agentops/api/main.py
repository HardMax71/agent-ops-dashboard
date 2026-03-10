from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentops.api.routers.auth import router as auth_router
from agentops.api.routers.internal import router as internal_router
from agentops.auth.middleware import SecurityHeadersMiddleware
from agentops.config import Settings, get_settings
from agentops.graphql.schema import graphql_app
from agentops.lifespan import lifespan

_VERSION = "0.1.0"


def create_app(settings: Settings, *, testing: bool = False) -> FastAPI:
    app = FastAPI(
        title="AgentOps Dashboard API",
        version=_VERSION,
        lifespan=None if testing else lifespan,
    )

    app.add_middleware(
        CORSMiddleware,  # type: ignore[invalid-argument-type]
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(SecurityHeadersMiddleware, frontend_origin=settings.frontend_origin)  # type: ignore[invalid-argument-type]

    app.include_router(auth_router)
    app.include_router(internal_router)
    app.include_router(graphql_app, prefix="/graphql")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": _VERSION}

    return app


app = create_app(get_settings())
