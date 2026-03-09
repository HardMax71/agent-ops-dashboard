from fastapi import FastAPI
from langserve import add_routes

from writer.chain import create_writer_chain


def create_app() -> FastAPI:
    app = FastAPI(title="Writer Agent", version="0.1.0")

    chain = create_writer_chain()
    add_routes(app, chain, path="/agents/writer")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent": "writer"}

    return app


app = create_app()
