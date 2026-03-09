from typing import Annotated

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph


async def get_graph(request: Request) -> CompiledStateGraph:
    return request.app.state.graph


GraphDep = Annotated[CompiledStateGraph, Depends(get_graph)]
