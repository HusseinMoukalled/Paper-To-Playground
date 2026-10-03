"""JSON Lines execution trace contracts and streaming writer."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO
from playground.secrets import redact_secrets


@dataclass(frozen=True, slots=True)
class TraceEvent:
    elapsed_seconds: float
    stage: str
    action: str
    result: str
    details: dict[str, Any] = field(default_factory=dict)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds cannot be negative")
        if not self.stage or not self.action or not self.result:
            raise ValueError("stage, action, and result are required")
        for name in ("prompt_tokens", "completion_tokens"):
            count = getattr(self, name)
            if count is not None and count < 0:
                raise ValueError(f"{name} cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        event: dict[str, Any] = {
            "elapsed_seconds": self.elapsed_seconds,
            "stage": self.stage,
            "action": self.action,
            "result": self.result,
            "details": self.details,
        }
        if self.prompt_tokens is not None:
            event["prompt_tokens"] = self.prompt_tokens
        if self.completion_tokens is not None:
            event["completion_tokens"] = self.completion_tokens
        return event


class TraceWriter:
    """Writes and flushes one valid JSON event per line."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._started_at = time.monotonic()
        self._stream: TextIO = self.path.open("w", encoding="utf-8", newline="\n")

    def emit(
        self,
        *,
        stage: str,
        action: str,
        result: str,
        details: dict[str, Any] | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            elapsed_seconds=max(0.0, time.monotonic() - self._started_at),
            stage=stage,
            action=action,
            result=result,
            details=details or {},
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        self._stream.write(json.dumps(redact_secrets(event.to_dict()), ensure_ascii=True, separators=(",", ":")))
        self._stream.write("\n")
        self._stream.flush()
        return event

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
