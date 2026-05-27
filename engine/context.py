from __future__ import annotations

from utils.llm.types import Message


class ContextManager:
    """Manages the persistent conversation context C (§3.3).

    Tracks the LLM context usage proportion and enforces the context
    cap β to prevent overflow. Accumulates skill versions, verification
    feedback, and oracle pass/fail bits.

    The context evolves as follows:
      C(0) = (I, S_meta)                    // initial context
      C(i+1) = C(i) ⊕ F(i,j)                // after verifier failure (Eq.7)
      C(i+1) = C(i) ⊕ 1[R(i)<1]             // oracle pass/fail bit
    """

    def __init__(self, beta: float = 0.7, max_tokens: int = 100000):
        self.beta = beta
        self.max_tokens = max_tokens
        self.messages: list[Message] = []
        self._estimated_tokens: int = 0

    def init(self, instruction: str, meta_skill: str = "") -> None:
        """Initialize context C(0) = (I, S_meta)."""
        self.messages = []
        self._estimated_tokens = 0

        content = instruction
        if meta_skill:
            content = f"{meta_skill}\n\n---\n\nTask Description:\n{instruction}"

        self.append(Message.user(content))

    def append(self, message: Message) -> None:
        """Append a message and update token estimate."""
        self.messages.append(message)
        self._estimated_tokens += _estimate_tokens(message.content or "")

    def append_feedback(self, feedback) -> None:
        """Append a failure diagnostic F(i,j) to context."""
        feedback_str = feedback.to_context_str() if hasattr(feedback, "to_context_str") else str(feedback)
        self.append(Message.user(feedback_str))

    def append_oracle_signal(self, score: float) -> None:
        """Append oracle score (no test content revealed)."""
        if score >= 1.0:
            signal = "Ground-truth oracle: ALL TESTS PASSED. Skill is ready for deployment."
        elif score > 0.0:
            signal = (
                f"Ground-truth oracle: {score * 100:.1f}% of tests passed. "
                f"The verifier must escalate its test suite to catch remaining issues."
            )
        else:
            signal = "Ground-truth oracle: ALL TESTS FAILED. The verifier's tests were insufficient."
        self.append(Message.user(signal))

    @property
    def usage_ratio(self) -> float:
        """Current context window usage proportion (0—1)."""
        return min(self._estimated_tokens / self.max_tokens, 1.0)

    @property
    def is_full(self) -> bool:
        """Whether context exceeds the cap β."""
        return self.usage_ratio > self.beta

    @property
    def size(self) -> int:
        return len(self.messages)


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate (~4 chars per token)."""
    return max(len(text) // 4, 1)
