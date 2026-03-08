from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI
from openai import RateLimitError

from critic.models import CritiqueFinding, map_critique_to_verdict

__all__ = ["create_critic_chain", "map_critique_to_verdict"]

_CRITIC_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a critical reviewer of software bug investigations.\n"
            "Review agent findings and determine if there is sufficient evidence to write a"
            " report.\n"
            "Be rigorous: require specific file locations, error reproducibility details, and"
            " clear root cause identification.\n"
            "Output verdict APPROVED only when all evidence is strong and ready_for_report is"
            " true.",
        ),
        (
            "human",
            "Findings: {findings}\nHypothesis: {hypothesis}\nHuman exchanges: {human_exchanges}\n\n"
            "Review these findings critically.",
        ),
    ]
)


def create_critic_chain() -> RunnableSerializable:
    """Create the critic chain. Call during app startup, not at import."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    primary = _CRITIC_PROMPT | llm.with_structured_output(CritiqueFinding)
    fallback = _CRITIC_PROMPT | ChatOpenAI(
        model="gpt-3.5-turbo", temperature=0
    ).with_structured_output(CritiqueFinding)
    return primary.with_retry(
        stop_after_attempt=3,
        retry_if_exception_type=(RateLimitError,),
    ).with_fallbacks([fallback])
