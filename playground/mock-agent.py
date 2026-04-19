"""
Minimal spec-driven agent skeleton. Starting point for a prototype.

Runs offline. No API keys. Copy the file, edit the spec, edit the agent
function, run. Swap in a real model by replacing `mock_model` with a
`litellm.completion(...)` call when ready.

Usage:
    python mock-agent.py
"""

from __future__ import annotations

from dataclasses import dataclass


SPEC = """\
Intent: answer short support questions from a fixed FAQ.
Invariants:
  - refuse if the question does not match a known shape.
  - never invent facts outside the FAQ.
Success: matched questions answered from the FAQ verbatim.
"""

FAQ: dict[str, str] = {
    "hours": "Support is available Monday to Friday, 09:00 to 17:00 CET.",
    "refund": "Refunds are issued within 5 working days of the request.",
    "status": "Check status.example.com for real-time incident updates.",
}


@dataclass
class AgentOutput:
    answer: str
    matched_key: str | None
    refused: bool


def mock_model(question: str) -> str | None:
    """Stand-in for a real LLM. Returns a FAQ key or None."""
    q = question.lower()
    for key in FAQ:
        if key in q:
            return key
    return None


def agent(question: str) -> AgentOutput:
    key = mock_model(question)
    if key is None:
        return AgentOutput(
            answer="I cannot answer that from the FAQ.",
            matched_key=None,
            refused=True,
        )
    return AgentOutput(answer=FAQ[key], matched_key=key, refused=False)


def main() -> None:
    print(SPEC)
    for question in [
        "What are your support hours?",
        "How do I get a refund?",
        "Can you write me a poem about kittens?",
    ]:
        out = agent(question)
        verdict = "REFUSED" if out.refused else f"matched={out.matched_key}"
        print(f"  Q: {question}")
        print(f"  A: {out.answer}")
        print(f"  [{verdict}]")
        print()


if __name__ == "__main__":
    main()
