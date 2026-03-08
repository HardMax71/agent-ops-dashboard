from langchain_core.callbacks import BaseCallbackHandler
from opentelemetry.sdk.metrics import MeterProvider

_MODEL_RATES: dict[str, float] = {
    "gpt-4o": 0.000005,  # $5 / 1M tokens (blended)
    "gpt-4o-mini": 0.000000150,  # $0.15 / 1M tokens (blended)
}
_DEFAULT_RATE: float = 0.000001  # conservative fallback


class AgentOpsMetricsCallback(BaseCallbackHandler):
    """LangChain callback handler for OTel metrics."""

    def __init__(self, job_id: str, agent_name: str, meter_provider: MeterProvider) -> None:
        self.job_id = job_id
        self.agent_name = agent_name
        self._current_model: str = ""
        meter = meter_provider.get_meter("agentops.agent")
        self._token_counter = meter.create_counter(
            "agentops_tokens_total",
            description="Total tokens consumed",
        )
        self._cost_counter = meter.create_counter(
            "agentops_cost_usd_total",
            description="Total cost in USD",
        )

    def on_llm_start(
        self, serialized: dict[str, object], prompts: list[str], **kwargs: object
    ) -> None:  # noqa: ANN401
        kwargs_dict = serialized.get("kwargs") or {}
        self._current_model = str(kwargs_dict.get("model_name") or "")

    def on_llm_end(self, response: object, **kwargs: object) -> None:  # noqa: ANN401
        usage = getattr(response, "llm_output", {}) or {}
        token_usage = usage.get("token_usage", {})
        total = token_usage.get("total_tokens", 0)
        self._token_counter.add(total, {"agent": self.agent_name})
        rate = _MODEL_RATES.get(self._current_model, _DEFAULT_RATE)
        self._cost_counter.add(total * rate, {"agent": self.agent_name})
