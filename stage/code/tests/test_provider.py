import json

from ghost_data.provider import ModelResponse, TokenLogger, TokenUsage


def test_response_validates_usage_and_logger_appends_jsonl(tmp_path):
    response = ModelResponse(
        content="classification text",
        usage=TokenUsage(input_tokens=12, output_tokens=3),
        provider="fake",
        model="unit-model",
    )
    path = tmp_path / "usage" / "calls.jsonl"
    logger = TokenLogger(path)
    logger.log(response)
    logger.log(response, cache_hit=True)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["input_tokens"] == 12
    assert rows[1]["cache_hit"] is True
    assert "content" not in rows[0]


def test_package_exports_provider_contract():
    from ghost_data import ProviderRequest

    request = ProviderRequest(model="local", system_prompt="policy", user_content="untrusted")
    assert request.model == "local"
