from fastapi import FastAPI
from langserve import add_routes

from codebase_search.chain import create_codebase_search_chain


def create_app() -> FastAPI:
    app = FastAPI(title="Codebase Search Agent", version="0.1.0")

    chain = create_codebase_search_chain()
    add_routes(app, chain, path="/agents/codebase_search")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent": "codebase_search"}

    return app


app = create_app()
