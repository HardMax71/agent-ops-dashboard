from typing import Annotated

from arq import ArqRedis
from fastapi import Depends
from starlette.requests import HTTPConnection


async def get_arq(connection: HTTPConnection) -> ArqRedis:
    return connection.app.state.arq


ArqDep = Annotated[ArqRedis, Depends(get_arq)]
