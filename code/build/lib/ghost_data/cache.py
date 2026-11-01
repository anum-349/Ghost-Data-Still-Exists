"""Content-addressed disk cache and provider decorator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .provider import ModelProvider, ModelResponse, ProviderRequest, TokenLogger, TokenUsage


def content_cache_key(provider: str, request: ProviderRequest) -> str:
    payload = {
        "provider": provider,
        "model": request.model,
        "system_prompt": request.system_prompt,
        "user_content": request.user_content,
        "metadata": request.metadata,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DiskResponseCache:
    """Store provider responses under SHA-256 content keys."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def get(self, key: str) -> ModelResponse | None:
        path = self.directory / f"{key}.json"
        if not path.is_file():
            return None
        return ModelResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def put(self, key: str, response: ModelResponse) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{key}.json"
        path.write_text(response.model_dump_json(), encoding="utf-8")


class CachedProvider:
    """Cache provider calls and record token usage for each request."""

    def __init__(self, provider: ModelProvider, cache: DiskResponseCache, logger: TokenLogger) -> None:
        self.provider = provider
        self.cache = cache
        self.logger = logger

    @property
    def name(self) -> str:
        return self.provider.name

    def complete(self, request: ProviderRequest) -> ModelResponse:
        key = content_cache_key(self.name, request)
        cached = self.cache.get(key)
        if cached is not None:
            self.logger.log(cached, cache_hit=True)
            return cached
        response = self.provider.complete(request)
        self.cache.put(key, response)
        self.logger.log(response)
        return response
