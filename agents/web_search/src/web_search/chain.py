from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI

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
    structured_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
        WebSearchFinding
    )
    return _SEARCH_PROMPT | structured_llm.with_retry(stop_after_attempt=3)
