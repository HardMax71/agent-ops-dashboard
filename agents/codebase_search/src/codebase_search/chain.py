from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI

from codebase_search.models import CodebaseFinding

_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
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
])

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
_structured_llm = _llm.with_structured_output(CodebaseFinding)

codebase_search_chain: RunnableSerializable = _ANALYSIS_PROMPT | _structured_llm.with_retry(
    stop_after_attempt=3
)
