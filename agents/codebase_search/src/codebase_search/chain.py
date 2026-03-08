from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI

from codebase_search.models import CodebaseFinding

_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a codebase analysis expert. Given a hypothesis and affected areas, "
            "provide a structured codebase finding with relevant files and root cause location.",
        ),
        (
            "human",
            "Repository: {repository}\nKeywords: {keywords}\nHypothesis: {hypothesis}\n"
            "Affected areas: {affected_areas}\n\nProvide your structured codebase finding.",
        ),
    ]
)


def create_codebase_search_chain() -> RunnableSerializable:
    """Create the codebase search chain. Call during app startup, not at import."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(CodebaseFinding)
    return _ANALYSIS_PROMPT | structured_llm.with_retry(stop_after_attempt=3)
