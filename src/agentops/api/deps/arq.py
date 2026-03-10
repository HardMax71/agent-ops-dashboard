from typing import Annotated

from arq import ArqRedis
from fastapi import Depends, Request


async def get_arq(request: Request) -> ArqRedis:
    return request.app.state.arq


ArqDep = Annotated[ArqRedis, Depends(get_arq)]
