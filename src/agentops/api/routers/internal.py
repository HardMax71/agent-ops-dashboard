from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from agentops.api.deps.settings import SettingsDep

router = APIRouter(prefix="/internal", tags=["internal"])


class LangSmithAlertBody(BaseModel):
    rule_id: str
    run_id: str
    event_type: str
    payload: dict


@router.post("/langsmith-alert")
async def langsmith_alert(
    body: LangSmithAlertBody,
    settings: SettingsDep,
    x_langsmith_secret: str = Header(default=""),
) -> dict[str, str]:
    """Handle LangSmith webhook alerts."""
    if x_langsmith_secret != settings.langsmith_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

    return {"status": "received", "rule_id": body.rule_id}
