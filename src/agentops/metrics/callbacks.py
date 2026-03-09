import time
import uuid

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import ChatGeneration, LLMResult
from opentelemetry.sdk.metrics import MeterProvider
from pydantic import BaseModel

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-3.5-turbo": {"input": 0.50 / 1_000_000, "output": 1.50 / 1_000_000},
}

AGENT_NAMES = {"investigator", "codebase_search", "web_search", "critic", "writer", "supervisor"}


class CallbackMetadata(BaseModel):
    """Typed subset of LangChain callback metadata."""

    langgraph_node: str = ""
    ls_model_name: str = ""


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
        self._runs: dict[str, tuple[float, str]] = {}

    def _agent_name(self, serialized: dict[str, object], metadata: CallbackMetadata) -> str | None:
        """Extract the LangGraph node name if this is a tracked agent."""
        name = metadata.langgraph_node or serialized.get("name", "")
        return str(name) if name in AGENT_NAMES else None

    def on_chain_start(
        self,
        serialized: dict[str, object],
        inputs: dict[str, object],
        *,
        run_id: uuid.UUID,
        metadata: dict[str, object] | None = None,
        **kwargs: object,  # noqa: ANN401 — LangChain callback protocol has untyped kwargs
    ) -> None:
        meta = CallbackMetadata.model_validate(metadata or {})
        agent = self._agent_name(serialized, meta)
        if agent:
            self._runs[str(run_id)] = (time.perf_counter(), agent)
            self._agent_calls.add(1, {"agent": agent})

    def on_chain_end(
        self,
        outputs: dict[str, object],
        *,
        run_id: uuid.UUID,
        **kwargs: object,  # noqa: ANN401 — LangChain callback protocol has untyped kwargs
    ) -> None:
        key = str(run_id)
        run_info = self._runs.pop(key, None)
        if run_info is not None:
            start_time, agent = run_info
            elapsed = time.perf_counter() - start_time
            self._agent_duration.record(elapsed, {"agent": agent})

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: object,  # noqa: ANN401 — LangChain callback protocol has untyped kwargs
    ) -> None:
        key = str(run_id)
        run_info = self._runs.pop(key, None)
        if run_info is not None:
            _, agent = run_info
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
        meta = CallbackMetadata.model_validate(kwargs.get("metadata") or {})
        model = meta.ls_model_name or "gpt-4o-mini"
        agent = meta.langgraph_node or "unknown"
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])

        generation: ChatGeneration = response.generations[0][0]  # type: ignore[assignment]
        usage = generation.message.usage_metadata  # type: ignore[unresolved-attribute]
        if usage:
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
            self._token_usage.add(
                input_tokens, {"agent": agent, "model": model, "token_type": "input"}
            )
            self._token_usage.add(
                output_tokens, {"agent": agent, "model": model, "token_type": "output"}
            )
            self._cost_usd.add(cost, {"agent": agent, "model": model})
