"""Injectable boundary to Developer 2's sole permitted model client.

An implementation must route through playground.model.client, use model_id
unchanged, delimit the candidate text as untrusted data, and perform exactly
one transport attempt. The model client owns call/token accounting and trace;
retrieval only checks that optional work can be afforded before delegation.
No OpenRouter transport or prompt generation is implemented here.
"""

from dataclasses import dataclass
from typing import Protocol

from playground.budget import RunBudget
from playground.trace import TraceWriter


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    element_id: str
    heading: str | None
    preview: str


@dataclass(frozen=True, slots=True)
class RerankRequest:
    model_id: str
    focus: str
    candidates: tuple[RerankCandidate, ...]
    max_completion_tokens: int = 256
    source_is_untrusted: bool = True


@dataclass(frozen=True, slots=True)
class RerankResult:
    selected_ids: tuple[str, ...]
    insufficient: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0


class RetrievalReranker(Protocol):
    def rerank(self, request: RerankRequest, *, budget: RunBudget,
               trace: TraceWriter | None = None) -> RerankResult:
        """The model client authorizes/counts one attempt, including failures.

        It uses a timeout bounded by the remaining global runtime, limits
        completion to request.max_completion_tokens, and records actual usage.
        Transport retries are disabled for this optional retrieval request.
        """
        ...
