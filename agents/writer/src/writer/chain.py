from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI

from writer.models import WriterOutput

_REPORT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a technical writer creating bug triage reports. "
            "Based on agent findings, write a comprehensive triage report. "
            "Always populate ticket_title (concise title for the bug ticket), "
            "ticket_labels (e.g. ['bug', 'priority:high']), "
            "and ticket_assignee (suggested GitHub username or team name).",
        ),
        (
            "human",
            "Issue: {issue_title}\nFindings: {findings}\nCritic feedback: {critic_feedback}\n"
            "Human exchanges: {human_exchanges}\n\nCreate a complete triage report. "
            "Include ticket_title, ticket_labels, and ticket_assignee in your output.",
        ),
    ]
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
_structured_llm = _llm.with_structured_output(WriterOutput)

writer_chain: RunnableSerializable = _REPORT_PROMPT | _structured_llm.with_retry(
    stop_after_attempt=3
)
