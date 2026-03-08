from typing import Annotated

from fastapi import Depends, Request
from opentelemetry.sdk.metrics import MeterProvider


async def get_meter_provider(request: Request) -> MeterProvider:
    return request.app.state.meter_provider


MeterProviderDep = Annotated[MeterProvider, Depends(get_meter_provider)]
