from ghost_data.cache import CachedProvider, DiskResponseCache, content_cache_key
from ghost_data.provider import ModelResponse, ProviderRequest, TokenLogger, TokenUsage


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        return ModelResponse(
            content="classification text",
            usage=TokenUsage(input_tokens=7, output_tokens=2),
            provider=self.name,
            model=request.model,
        )


def test_content_key_is_stable_and_tracks_prompt_content():
    request = ProviderRequest(model="m", system_prompt="s", user_content="one")
    equivalent = ProviderRequest(model="m", system_prompt="s", user_content="one")
    changed = ProviderRequest(model="m", system_prompt="s", user_content="two")
    assert content_cache_key("p", request) == content_cache_key("p", equivalent)
    assert content_cache_key("p", request) != content_cache_key("p", changed)


def test_disk_cache_avoids_duplicate_provider_call_and_logs_each_request(tmp_path):
    backend = FakeProvider()
    provider = CachedProvider(
        backend,
        DiskResponseCache(tmp_path / "cache"),
        TokenLogger(tmp_path / "usage.jsonl"),
    )
    request = ProviderRequest(model="m", system_prompt="s", user_content="input")

    first = provider.complete(request)
    second = provider.complete(request)

    assert first == second
    assert backend.calls == 1
    assert len((tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()) == 2
