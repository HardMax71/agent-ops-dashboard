from fastapi import FastAPI
from langserve import add_routes

from web_search.chain import create_web_search_chain


def create_app() -> FastAPI:
    app = FastAPI(title="Web Search Agent", version="0.1.0")

    chain = create_web_search_chain()
    add_routes(app, chain, path="/agents/web_search")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent": "web_search"}

    return app


app = create_app()
