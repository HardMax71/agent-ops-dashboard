from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agentops.graph.state import BugTriageState

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


class SupervisorDecision(BaseModel):
    next_agent: str
    reasoning: str
    confidence: float = 0.0
    question_for_human: str = ""


_SUPERVISOR_PROMPT = ChatPromptTemplate.from_messages([
    ("human", _SUPERVISOR_PROMPT_TEMPLATE),
])


def build_supervisor_context(state: BugTriageState) -> dict:
    findings_block = "\n".join(
        f"- [{f.agent_name}] {f.summary} (confidence: {f.confidence:.2f})"
        for f in state.findings
    ) or "No findings yet"

    human_exchanges_block = "\n".join(
        f"Q: {e.question}\nA: {e.answer}"
        for e in state.human_exchanges
    ) or "No exchanges yet"

    agent_names = ", ".join({f.agent_name for f in state.findings}) or "none"
    critic_verdict = state.critic_feedback.verdict if state.critic_feedback else "none"

    return {
        "iterations": state.iterations,
        "max_iterations": state.max_iterations,
        "findings_count": len(state.findings),
        "agent_names": agent_names,
        "human_exchanges_count": len(state.human_exchanges),
        "critic_verdict": critic_verdict,
        "findings_block": findings_block,
        "human_exchanges_block": human_exchanges_block,
    }


def route_from_supervisor(state: BugTriageState) -> Literal[
    "investigator", "codebase_search", "web_search", "critic", "human_input", "writer", "end"
]:
    """Route based on supervisor decision with 5 guards."""
    # G1: first iteration always goes to investigator
    if state.iterations == 0:
        return "investigator"

    # G3: max iterations forces writer
    if state.iterations >= state.max_iterations:
        return "writer"

    # G4: end node without report forces writer
    if state.supervisor_next == "end" and state.report is None:
        return "writer"

    # G5: critic rejected → back to investigator (unless G3)
    if (
        state.critic_feedback is not None
        and state.critic_feedback.verdict == "REJECTED"
        and state.supervisor_next == "writer"
    ):
        return "investigator"

    # G2: too many human exchanges → skip human_input
    if state.supervisor_next == "human_input" and len(state.human_exchanges) >= 2:
        return "investigator"

    next_agent = state.supervisor_next
    valid_nodes = {"investigator", "codebase_search", "web_search", "critic", "human_input", "writer", "end"}
    if next_agent in valid_nodes:
        return next_agent  # type: ignore[return-value]
    return "investigator"


async def _invoke_supervisor(state: BugTriageState) -> SupervisorDecision:
    """Invoke LLM supervisor."""
    llm = ChatOpenAI(model="gpt-4o")
    structured = llm.with_structured_output(SupervisorDecision)
    context = build_supervisor_context(state)
    result = await structured.ainvoke(_SUPERVISOR_PROMPT.format_messages(**context))
    return result  # type: ignore[return-value]


async def supervisor_node(state: BugTriageState) -> BugTriageState:
    """Full supervisor node with LLM routing."""
    decision = await _invoke_supervisor(state)
    return state.model_copy(update={
        "supervisor_next": decision.next_agent,
        "supervisor_reasoning": decision.reasoning,
        "supervisor_confidence": decision.confidence,
        "current_node": "supervisor",
        "iterations": state.iterations + 1,
    })
