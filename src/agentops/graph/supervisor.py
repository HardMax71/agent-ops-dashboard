from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agentops.graph.state import BugTriageState


class SupervisorDecision(BaseModel):
    next_agent: Literal[
        "investigator", "codebase_search", "web_search", "critic", "human_input", "writer", "end"
    ]
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    question_for_human: str = ""


_SUPERVISOR_PROMPT_TEMPLATE = """You are the supervisor orchestrating a bug triage investigation.

Current state:
- Iterations: {iterations}/{max_iterations}
- Current findings: {findings_count} findings from agents: {agent_names}
- Human exchanges: {human_exchanges_count}
- Critic feedback: {critic_verdict}

Agent findings summary:
{findings_block}

Human exchanges:
{human_exchanges_block}

Based on the current state, decide which agent should run next:
- investigator: initial analysis, re-investigation after rejection
- codebase_search: search codebase for relevant files
- web_search: search web for related issues/solutions
- critic: review findings for completeness
- human_input: ask human for clarification (max 2 exchanges)
- writer: write final report (when findings are sufficient)
- end: investigation complete (only after writer)

Choose the most appropriate next agent."""

_SUPERVISOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are the supervisor of a bug triage system. Decide which agent runs next."),
    ("human", _SUPERVISOR_PROMPT_TEMPLATE),
])


def build_supervisor_context(state: BugTriageState) -> dict[str, object]:  # noqa: ANN401
    findings_block = "\n".join(
        f"- [{f.agent_name}] {f.summary} (confidence: {f.confidence:.2f})"
        for f in state.findings
    )
    human_exchanges_block = "\n".join(
        f"Q: {e.question}\nA: {e.answer}"
        for e in state.human_exchanges
    )
    agent_names = list({f.agent_name for f in state.findings})
    critic_verdict = state.critic_feedback.verdict if state.critic_feedback else "none"

    return {
        "iterations": state.iterations,
        "max_iterations": state.max_iterations,
        "findings_count": len(state.findings),
        "agent_names": ", ".join(agent_names) if agent_names else "none",
        "human_exchanges_count": len(state.human_exchanges),
        "critic_verdict": critic_verdict,
        "findings_block": findings_block or "No findings yet",
        "human_exchanges_block": human_exchanges_block or "No exchanges yet",
    }


def route_from_supervisor(state: BugTriageState) -> str:
    """Route based on supervisor decision with 5 guards."""
    # G1: First iteration always goes to investigator
    if state.iterations == 0:
        return "investigator"

    # G3: Max iterations reached → force writer
    if state.iterations >= state.max_iterations:
        return "writer"

    # G4: No report yet and supervisor says end → force writer
    if state.supervisor_next == "end" and state.report is None:
        return "writer"

    # G5: Critic rejected and supervisor wants writer → re-investigate (bypassed by G3)
    if (
        state.critic_feedback is not None
        and state.critic_feedback.verdict == "REJECTED"
        and state.supervisor_next == "writer"
        and state.iterations < state.max_iterations
    ):
        return "investigator"

    # G2: Too many human exchanges, force forward
    if len(state.human_exchanges) >= 2 and state.supervisor_next == "human_input":
        return "writer"

    next_node = state.supervisor_next
    valid_nodes = (
        "investigator", "codebase_search", "web_search", "critic", "human_input", "writer"
    )
    if next_node in valid_nodes:
        return next_node
    return "writer"


async def _invoke_supervisor(state: BugTriageState) -> SupervisorDecision:
    """Invoke LLM supervisor."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(SupervisorDecision)
    chain = _SUPERVISOR_PROMPT | structured_llm
    context = build_supervisor_context(state)
    decision: SupervisorDecision = await chain.ainvoke(context)
    return decision


async def supervisor_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Full supervisor node with LLM routing."""
    decision = await _invoke_supervisor(state)
    return {
        "supervisor_next": decision.next_agent,
        "supervisor_confidence": decision.confidence,
        "supervisor_reasoning": decision.reasoning,
    }
