import json
from pathlib import Path

import pytest

from ghost_data.cache import CachedProvider, DiskResponseCache
from ghost_data.provider import ModelResponse, ProviderRequest, TokenLogger, TokenUsage
from ghost_data.request_classifier import RequestClassifier, deterministic_classification


@pytest.mark.parametrize("text", [
    "Please delete my account and personal data.",
    "Quiero que eliminen mis datos personales.",
    "Je demande l’effacement de mes données personnelles.",
    "Bitte löschen Sie mein Konto.",
    "Quero apagar meus dados pessoais.",
    "Please check whether any personal data remains and complete deletion if needed.",
    "¿Pueden comprobar si todavía queda algún dato y completar la eliminación si hace falta?",
    "Veuillez vérifier s’il reste des données et terminer leur suppression si nécessaire.",
])
def test_deletion_and_indirect_intent_are_deterministic(text):
    result = deterministic_classification(text)
    assert result is not None and result.requests_deletion is True


@pytest.mark.parametrize("text", [
    "I do not want you to delete my account.",
    "Please cancel my deletion request.",
    "No quiero que eliminen mis datos.",
    "Je ne veux pas que vous supprimiez mon compte.",
    "Bitte löschen Sie mein Konto nicht.",
    "Non voglio che cancelliate i miei dati.",
    "Não quero que apaguem meus dados.",
])
def test_clear_declines_are_deterministic(text):
    result = deterministic_classification(text)
    assert result is not None and result.requests_deletion is False


@pytest.mark.parametrize("text", [
    "Please send me a copy of my personal data.",
    "Quiero acceder a mis datos personales.",
    "Je souhaite accéder à mes données personnelles.",
    "Ich möchte eine Kopie meiner Daten.",
    "Quero acessar meus dados.",
    "Please correct my email address.",
    "Veuillez corriger mon adresse.",
])
def test_access_and_correction_only_are_deterministic(text):
    result = deterministic_classification(text)
    assert result is not None and result.requests_deletion is False


class FakeProvider:
    name = "fake"

    def __init__(self, content):
        self.content = content
        self.calls = []

    def complete(self, request: ProviderRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(
            content=self.content,
            usage=TokenUsage(input_tokens=11, output_tokens=7),
            provider=self.name,
            model=request.model,
        )


def make_classifier(tmp_path: Path, content: str):
    backend = FakeProvider(content)
    wrapped = CachedProvider(
        backend,
        DiskResponseCache(tmp_path / "cache"),
        TokenLogger(tmp_path / "usage.jsonl"),
    )
    return RequestClassifier(wrapped, model="fixture-model"), backend


def test_uncertain_text_uses_strict_temperature_zero_cached_llm(tmp_path):
    content = json.dumps({"requests_deletion": False, "confidence": 0.95, "reason": "Only an access request."})
    classifier, backend = make_classifier(tmp_path, content)
    first = classifier.classify("I only need a copy of the information you hold.")
    second = classifier.classify("I only need a copy of the information you hold.")
    assert first.requests_deletion is False and second == first
    assert len(backend.calls) == 1
    request = backend.calls[0]
    assert request.metadata["temperature"] == "0"
    schema = json.loads(request.metadata["json_schema"])
    assert set(schema["properties"]) == {"requests_deletion", "confidence", "reason"}
    assert schema["additionalProperties"] is False
    assert len((tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_low_confidence_model_non_deletion_defaults_to_deletion(tmp_path):
    classifier, _ = make_classifier(
        tmp_path,
        json.dumps({"requests_deletion": False, "confidence": 0.55, "reason": "Possibly access only."}),
    )
    assert classifier.classify("Please take care of my request.").requests_deletion is True


@pytest.mark.parametrize("content", [
    "not json",
    json.dumps({"requests_deletion": False, "confidence": 1.0, "reason": "No", "extra": "field"}),
])
def test_invalid_model_output_defaults_to_deletion(tmp_path, content):
    classifier, _ = make_classifier(tmp_path, content)
    assert classifier.classify("Please take care of my request.").requests_deletion is True


def test_without_provider_defaults_to_deletion():
    assert RequestClassifier().classify("Please take care of my request.").requests_deletion is True

