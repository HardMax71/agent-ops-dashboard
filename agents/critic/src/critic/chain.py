from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI

from critic.models import CritiqueFinding, map_critique_to_verdict

__all__ = ["critic_chain", "map_critique_to_verdict"]

_CRITIC_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a critical reviewer of software bug investigations.\n"
        "Review agent findings and determine if there is sufficient evidence to write a report.\n"
        "Be rigorous: require specific file locations, error reproducibility details, and clear "
        "root cause identification.\n"
        "Output verdict APPROVED only when all evidence is strong and ready_for_report is true.",
    ),
    (
        "human",
        "Findings: {findings}\nHypothesis: {hypothesis}\nHuman exchanges: {human_exchanges}\n\n"
        "Review these findings critically.",
    ),
])

_structured_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
    CritiqueFinding
)

critic_chain: RunnableSerializable = _CRITIC_PROMPT | _structured_llm.with_retry(
    stop_after_attempt=3
)
