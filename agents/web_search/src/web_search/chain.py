from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI
from openai import RateLimitError

from web_search.models import WebSearchFinding

_SEARCH_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a web search expert analyzing software bugs. Search for relevant information "
            "about the issue and provide structured findings.",
        ),
        (
            "human",
            "Issue: {issue_title}\nHypothesis: {hypothesis}\nKeywords: {keywords_for_search}\n"
            "Error messages: {error_messages}\n\n"
            "Provide web search findings with relevant links and analysis.",
        ),
    ]
)


def create_web_search_chain() -> RunnableSerializable:
    """Create the web search chain. Call during app startup, not at import."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # type: ignore[unknown-argument]
    primary = _SEARCH_PROMPT | llm.with_structured_output(WebSearchFinding)
    fallback = _SEARCH_PROMPT | ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0,  # type: ignore[unknown-argument]
    ).with_structured_output(WebSearchFinding)
    return primary.with_retry(
        stop_after_attempt=3,
        retry_if_exception_type=(RateLimitError,),
    ).with_fallbacks([fallback])
