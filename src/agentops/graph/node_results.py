from typing import TypedDict

from agentops.graph.state import AgentFinding, CriticFeedback, HumanExchange, TriageReport


class AgentNodeResult(TypedDict):
    findings: list[AgentFinding]
    current_node: str
    iterations: int


class CriticNodeResult(TypedDict):
    findings: list[AgentFinding]
    critic_feedback: CriticFeedback
    current_node: str
    iterations: int


class WriterNodeResult(TypedDict):
    report: TriageReport
    current_node: str
    status: str


class HumanInputNodeResult(TypedDict):
    human_exchanges: list[HumanExchange]
    pending_exchange: None
    awaiting_human: bool
    current_node: str
    iterations: int


class SupervisorNodeResult(TypedDict, total=False):
    supervisor_next: str
    supervisor_confidence: float
    supervisor_reasoning: str
    pending_exchange: HumanExchange
    awaiting_human: bool


class SupervisorPromptContext(TypedDict):
    iterations: int
    max_iterations: int
    findings_count: int
    agent_names: str
    human_exchanges_count: int
    critic_verdict: str
    findings_block: str
    human_exchanges_block: str
    redirect_instructions_block: str
