from fastapi import FastAPI
from langserve import add_routes

from critic.chain import critic_chain


def create_app() -> FastAPI:
    app = FastAPI(title="Critic Agent", version="0.1.0")
    add_routes(app, critic_chain, path="/agents/critic")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent": "critic"}

    return app


app = create_app()
