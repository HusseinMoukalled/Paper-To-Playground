"""Bounded source/retrieval settings, independent of model configuration."""

from dataclasses import dataclass

from playground.config import MAX_EVIDENCE_CHUNKS, MAX_EVIDENCE_TOKENS, SOURCE_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class SourceSettings:
    timeout_seconds: float = SOURCE_TIMEOUT_SECONDS
    max_bytes: int = 32 * 1024 * 1024
    max_pages: int = 500
    max_elements: int = 30_000
    max_extracted_characters: int = 4_000_000
    max_redirects: int = 3
    transient_retries: int = 1
    max_evidence_chunks: int = MAX_EVIDENCE_CHUNKS
    max_evidence_tokens: int = MAX_EVIDENCE_TOKENS
    candidate_limit: int = 5
    preview_characters: int = 320
    neighbor_radius: int = 1
    max_visual_items: int = 128

    def __post_init__(self) -> None:
        for name in ("timeout_seconds", "max_bytes", "max_pages", "max_elements", "max_extracted_characters",
                     "max_evidence_chunks", "max_evidence_tokens", "candidate_limit",
                     "preview_characters", "max_visual_items"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_redirects < 0 or self.transient_retries not in (0, 1):
            raise ValueError("Redirects must be bounded; at most one retry is allowed")
        if self.neighbor_radius not in (0, 1):
            raise ValueError("At most one immediate neighborhood may be expanded")
