"""Lightweight deterministic lexical/BM25 index over canonical source elements."""

from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = frozenset("the a an and or of to in for with by on is are how why described shown mechanism section equation figure table this that it".split())


def tokenize(text: str) -> list[str]:
    return [word for word in re.findall(r"[^\W_]+(?:_[^\W_]+)*", text.casefold()) if word not in STOPWORDS]


def searchable_text(element) -> str:
    rows = element.metadata.get("rows", [])
    cells = " ".join(str(cell) for row in rows for cell in row if cell is not None)
    labels = element.metadata.get("labels", [])
    labels = " ".join(label.get("text", "") if isinstance(label, dict) else str(label) for label in labels)
    return " ".join((element.content, element.section_title or "", cells, labels))


class BM25Index:
    """Okapi BM25 with conventional k1/b parameters; no semantic service."""

    def __init__(self, elements, *, k1: float = 1.5, b: float = .75):
        self.elements = tuple(elements)
        self.documents = [Counter(tokenize(searchable_text(element))) for element in self.elements]
        self.lengths = [sum(document.values()) for document in self.documents]
        self.average_length = sum(self.lengths) / max(1, len(self.lengths))
        self.frequency = Counter(term for document in self.documents for term in document)
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        terms = set(tokenize(query))
        count = len(self.documents)
        scores = []
        for document, length, element in zip(self.documents, self.lengths, self.elements):
            score = 0.0
            for term in terms:
                frequency = document[term]
                if not frequency:
                    continue
                df = self.frequency[term]
                idf = math.log(1 + (count - df + .5) / (df + .5))
                norm = frequency + self.k1 * (1 - self.b + self.b * length / (self.average_length or 1))
                score += idf * frequency * (self.k1 + 1) / norm
            scores.append(score * (.05 if element.metadata.get("noise") else 1))
        return scores
