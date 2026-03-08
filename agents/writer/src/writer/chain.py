from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI

from writer.models import WriterOutput

_REPORT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a technical writer creating bug triage reports. "
            "Based on agent findings, write a comprehensive triage report.",
        ),
        (
            "human",
            "Issue: {issue_title}\nFindings: {findings}\nCritic feedback: {critic_feedback}\n"
            "Human exchanges: {human_exchanges}\n\nCreate a complete triage report.",
        ),
    ]
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
_structured_llm = _llm.with_structured_output(WriterOutput)

writer_chain: RunnableSerializable = _REPORT_PROMPT | _structured_llm.with_retry(
    stop_after_attempt=3
)
