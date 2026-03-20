import secrets

from fastapi import APIRouter, Header, HTTPException, status
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
    secret_header: str = Header(default="", alias="X-Webhook-Secret"),
) -> dict[str, str]:
    """Handle LangSmith webhook alerts. Auth via X-Webhook-Secret header (PRD-005-1)."""
    expected = settings.langsmith_webhook_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="LangSmith webhook secret not configured",
        )
    if not secret_header or not secrets.compare_digest(secret_header, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret",
        )

    return {"status": "received", "rule_id": body.rule_id}
