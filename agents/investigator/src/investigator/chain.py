from investigator.models import InvestigatorFinding
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI
from openai import RateLimitError

_INVESTIGATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert software investigator analyzing GitHub issues.
Given a bug report or issue, produce a structured analysis including:
- A clear hypothesis about the root cause
- Affected areas of the codebase
- Keywords useful for searching the codebase
- Error messages mentioned or implied
Be precise and technical. Base your analysis solely on the provided information.""",
        ),
        (
            "human",
            """Issue URL: {issue_url}
Title: {issue_title}
Body: {issue_body}
Repository: {repository}

Analyze this issue and provide your investigator findings.""",
        ),
    ]
)


def create_investigator_chain() -> RunnableSerializable:
    """Create the investigator chain. Call during app startup, not at import."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # type: ignore[unknown-argument]
    primary = _INVESTIGATOR_PROMPT | llm.with_structured_output(InvestigatorFinding)
    fallback = _INVESTIGATOR_PROMPT | ChatOpenAI(
        model="gpt-4o-mini",  # type: ignore[unknown-argument]
        temperature=0,
    ).with_structured_output(InvestigatorFinding)
    return primary.with_retry(
        stop_after_attempt=3,
        retry_if_exception_type=(RateLimitError,),
    ).with_fallbacks([fallback])
