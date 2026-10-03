"""Categorical confidence from observable signals, without pseudo-probabilities."""

from playground.retrieval.evidence import RetrievalConfidence


def classify_confidence(*, explicit_matches: int, unresolved_references: int,
                        exact_matches: int, positive_candidates: int,
                        top_term_coverage: float, tied_top: bool) -> RetrievalConfidence:
    # Structural decisions avoid asserting empirically uncalibrated probabilities.
    if unresolved_references:
        return RetrievalConfidence.LOW
    if explicit_matches:
        return RetrievalConfidence.HIGH
    if positive_candidates == 0 or top_term_coverage == 0:
        return RetrievalConfidence.LOW
    if exact_matches == 1 or (top_term_coverage == 1 and not tied_top):
        return RetrievalConfidence.HIGH
    return RetrievalConfidence.AMBIGUOUS
