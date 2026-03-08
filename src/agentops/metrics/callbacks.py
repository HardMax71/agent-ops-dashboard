import time
import uuid

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from opentelemetry.sdk.metrics import MeterProvider

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}

AGENT_NAMES = {"investigator", "codebase_search", "web_search", "critic", "writer", "supervisor"}


class AgentOpsMetricsCallback(BaseCallbackHandler):
    """LangChain callback handler for OTel metrics.

    Records agent invocations, durations, errors, token usage, and cost
    via the OTel Metrics API. Injected into the ARQ worker config; business
    logic has zero metric calls.
    """

    def __init__(self, meter_provider: MeterProvider) -> None:
        meter = meter_provider.get_meter("agentops")
        self._agent_calls = meter.create_counter(
            "agent_calls_total",
            description="Total agent invocations",
        )
        self._agent_duration = meter.create_histogram(
            "agent_duration_seconds",
            description="Per-agent execution time",
            unit="s",
        )
        self._agent_errors = meter.create_counter(
            "agent_errors_total",
            description="Total agent errors",
        )
        self._token_usage = meter.create_counter(
            "token_usage_total",
            description="Total tokens consumed",
        )
        self._cost_usd = meter.create_counter(
            "cost_usd_total",
            description="Total LLM cost in USD",
        )
        self._start_times: dict[str, float] = {}

    def _agent_name(self, serialized: dict[str, object], kwargs: dict[str, object]) -> str | None:
        """Extract the LangGraph node name if this is a tracked agent."""
        metadata = kwargs.get("metadata") or {}
        name = (
            metadata.get("langgraph_node")  # type: ignore[union-attr]
            or serialized.get("name", "")
        )
        return str(name) if name in AGENT_NAMES else None

    def on_chain_start(
        self,
        serialized: dict[str, object],
        inputs: dict[str, object],
        *,
        run_id: uuid.UUID,
        **kwargs: object,  # noqa: ANN401 — LangChain callback protocol has untyped kwargs
    ) -> None:
        agent = self._agent_name(serialized, kwargs)
        if agent:
            self._start_times[str(run_id)] = time.perf_counter()
            self._agent_calls.add(1, {"agent": agent})

    def on_chain_end(
        self,
        outputs: dict[str, object],
        *,
        run_id: uuid.UUID,
        **kwargs: object,  # noqa: ANN401 — LangChain callback protocol has untyped kwargs
    ) -> None:
        key = str(run_id)
        if key in self._start_times:
            elapsed = time.perf_counter() - self._start_times.pop(key)
            metadata = kwargs.get("metadata") or {}
            agent = str(metadata.get("langgraph_node") or "unknown")  # type: ignore[union-attr]
            self._agent_duration.record(elapsed, {"agent": agent})

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: object,  # noqa: ANN401 — LangChain callback protocol has untyped kwargs
    ) -> None:
        self._start_times.pop(str(run_id), None)
        metadata = kwargs.get("metadata") or {}
        agent = str(metadata.get("langgraph_node") or "unknown")  # type: ignore[union-attr]
        if agent in AGENT_NAMES:
            self._agent_errors.add(1, {"agent": agent})

    def on_llm_start(
        self,
        serialized: dict[str, object],
        prompts: list[str],
        **kwargs: object,  # noqa: ANN401 — LangChain callback protocol has untyped kwargs
    ) -> None:
        pass

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        **kwargs: object,  # noqa: ANN401 — LangChain callback protocol has untyped kwargs
    ) -> None:
        metadata = kwargs.get("metadata") or {}
        model = str(metadata.get("ls_model_name") or "gpt-4o-mini")  # type: ignore[union-attr]
        agent = str(metadata.get("langgraph_node") or "unknown")  # type: ignore[union-attr]
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])

        usage = response.llm_output or {}
        usage_metadata = usage.get("usage_metadata") or {}
        input_tokens: int = usage_metadata.get("input_tokens", 0)  # type: ignore[assignment]
        output_tokens: int = usage_metadata.get("output_tokens", 0)  # type: ignore[assignment]
        cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]

        if input_tokens or output_tokens:
            self._token_usage.add(
                input_tokens, {"agent": agent, "model": model, "token_type": "input"}
            )
            self._token_usage.add(
                output_tokens, {"agent": agent, "model": model, "token_type": "output"}
            )
            self._cost_usd.add(cost, {"agent": agent, "model": model})
