from langchain_core.callbacks import BaseCallbackHandler
from opentelemetry import metrics

_meter = metrics.get_meter("agentops.agent")

_job_counter = _meter.create_counter(
    "agentops_jobs_total",
    description="Total jobs processed",
)
_token_counter = _meter.create_counter(
    "agentops_tokens_total",
    description="Total tokens consumed",
)
_cost_counter = _meter.create_counter(
    "agentops_cost_usd_total",
    description="Total cost in USD",
)


class AgentOpsMetricsCallback(BaseCallbackHandler):
    """LangChain callback handler for OTel metrics."""

    def __init__(self, job_id: str, agent_name: str) -> None:
        self.job_id = job_id
        self.agent_name = agent_name

    def on_llm_end(self, response: object, **kwargs: object) -> None:  # noqa: ANN401
        usage = getattr(response, "llm_output", {}) or {}
        token_usage = usage.get("token_usage", {})
        total = token_usage.get("total_tokens", 0)
        _token_counter.add(
            total,
            {"job_id": self.job_id, "agent": self.agent_name},
        )
        cost_usd = total * 0.000001  # ~$0.001 per 1000 tokens (gpt-4o-mini rate)
        _cost_counter.add(cost_usd, {"job_id": self.job_id, "agent": self.agent_name})
