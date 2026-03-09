from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from agentops.api.deps.settings import SettingsDep

router = APIRouter(prefix="/internal", tags=["internal"])


class LangSmithAlertBody(BaseModel):
    rule_id: str
    run_id: str
    event_type: str
    payload: dict[str, object]  # noqa: ANN401 — webhook payload is untyped


@router.post("/langsmith-alert")
async def langsmith_alert(
    body: LangSmithAlertBody,
    settings: SettingsDep,
    secret: str = Query(default=""),
) -> dict[str, str]:
    """Handle LangSmith webhook alerts. Auth via query param ?secret= (PRD-005-1)."""
    if not secret or secret != settings.langsmith_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret",
        )

    return {"status": "received", "rule_id": body.rule_id}
