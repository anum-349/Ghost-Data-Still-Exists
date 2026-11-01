"""Provider-neutral LLM contract and append-only token usage logging."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProviderRequest(BaseModel):
    """Inputs passed to an LLM provider. Prompt data is never trusted as policy."""

    model_config = ConfigDict(frozen=True)

    model: str
    system_prompt: str
    user_content: str
    metadata: dict[str, str] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    usage: TokenUsage
    provider: str
    model: str


class ModelProvider(Protocol):
    """Implement this interface to plug in any model vendor or local model."""

    @property
    def name(self) -> str: ...

    def complete(self, request: ProviderRequest) -> ModelResponse: ...


class TokenLogger:
    """Append one redacted usage record per actual provider call as JSONL."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def log(self, response: ModelResponse, *, cache_hit: bool = False) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": response.provider,
            "model": response.model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_hit": cache_hit,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


# Kept as an explicit alias for report consumers.
ModelUsage = TokenUsage
