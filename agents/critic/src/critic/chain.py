from typing import Literal

from langchain_openai import ChatOpenAI

from critic.models import CritiqueFinding, map_critique_to_verdict

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=3)
critic_chain = _llm.with_structured_output(CritiqueFinding)


def map_verdict(finding: CritiqueFinding) -> Literal["APPROVED", "REJECTED"]:
    """CONFIRMED + ready_for_report=True → APPROVED, else REJECTED."""
    return map_critique_to_verdict(finding)
