from fastapi import FastAPI
from investigator.chain import investigator_chain
from langserve import add_routes


def create_app() -> FastAPI:
    app = FastAPI(title="Investigator Agent", version="0.1.0")

    add_routes(app, investigator_chain, path="/agents/investigator")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent": "investigator"}

    return app


app = create_app()
