from __future__ import annotations

import json
from dataclasses import dataclass, field

from mini_code.config import AppConfig
from mini_code import llm


@dataclass
class FakeUsage:
    input_tokens: int = 12
    output_tokens: int = 34


@dataclass
class FakeResponse:
    content: list[dict]
    stop_reason: str
    id: str = "msg_123"
    model: str = "test-model"
    role: str = "assistant"
    type: str = "message"
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessagesAPI:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def create(self, **payload):
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return self.response


class FakeAnthropic:
    next_messages_api: FakeMessagesAPI | None = None

    def __init__(self, base_url=None):
        assert FakeAnthropic.next_messages_api is not None
        self.base_url = base_url
        self.messages = FakeAnthropic.next_messages_api


def test_provider_logs_structured_interaction(monkeypatch, tmp_path):
    response = FakeResponse(content=[{"type": "text", "text": "hello"}], stop_reason="end_turn")
    fake_api = FakeMessagesAPI(response=response)
    monkeypatch.setattr(llm, "Anthropic", FakeAnthropic)
    FakeAnthropic.next_messages_api = fake_api
    config = AppConfig(workdir=tmp_path, model_id="test-model", session_id="session-123")

    provider = llm.AnthropicProvider(config)
    provider.create_message(
        system="system prompt",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "demo"}],
        max_tokens=256,
    )

    lines = config.llm_session_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["session_id"] == "session-123"
    assert record["request"]["omitted_prefix_chars"] == 0
    assert record["response"]["omitted_prefix_chars"] == 0
    request_payload = json.loads(record["request"]["content"])
    response_payload = json.loads(record["response"]["content"])
    assert request_payload["model"] == "test-model"
    assert request_payload["system"] == "system prompt"
    assert request_payload["messages"] == [{"role": "user", "content": "hi"}]
    assert response_payload["stop_reason"] == "end_turn"
    assert response_payload["content"] == [{"type": "text", "text": "hello"}]
    assert response_payload["usage"] == {"input_tokens": 12, "output_tokens": 34}
    assert record["error"] is None


def test_provider_logs_errors_before_raising(monkeypatch, tmp_path):
    fake_api = FakeMessagesAPI(error=RuntimeError("boom"))
    monkeypatch.setattr(llm, "Anthropic", FakeAnthropic)
    FakeAnthropic.next_messages_api = fake_api
    config = AppConfig(workdir=tmp_path, model_id="test-model", session_id="session-456")

    provider = llm.AnthropicProvider(config)

    try:
        provider.create_message(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            max_tokens=64,
        )
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected RuntimeError")

    lines = config.llm_session_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["session_id"] == "session-456"
    assert record["response"] is None
    assert record["error"]["omitted_prefix_chars"] == 0
    assert json.loads(record["error"]["content"]) == {"type": "RuntimeError", "message": "boom"}


def test_provider_logs_only_suffix_after_shared_prefix(monkeypatch, tmp_path):
    responses = [
        FakeResponse(content=[{"type": "text", "text": "hello"}], stop_reason="end_turn"),
        FakeResponse(content=[{"type": "text", "text": "hello again"}], stop_reason="end_turn"),
    ]
    fake_api = FakeMessagesAPI()
    fake_api.response = responses[0]
    monkeypatch.setattr(llm, "Anthropic", FakeAnthropic)
    FakeAnthropic.next_messages_api = fake_api
    config = AppConfig(workdir=tmp_path, model_id="test-model", session_id="session-789")
    provider = llm.AnthropicProvider(config)

    provider.create_message(
        system="system prompt",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "demo"}],
        max_tokens=256,
    )
    fake_api.response = responses[1]
    provider.create_message(
        system="system prompt",
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
            {"role": "user", "content": "follow up"},
        ],
        tools=[{"name": "demo"}],
        max_tokens=256,
    )

    first_record, second_record = [
        json.loads(line)
        for line in config.llm_session_log_path.read_text(encoding="utf-8").splitlines()
    ]
    first_request = json.dumps(llm._json_safe(fake_api.calls[0]), ensure_ascii=False, sort_keys=True)
    second_request_full = json.dumps(llm._json_safe(fake_api.calls[1]), ensure_ascii=False, sort_keys=True)
    second_request = second_record["request"]
    assert first_record["request"]["content"] == first_request
    assert second_request["omitted_prefix_chars"] == llm._shared_prefix_length(
        first_request,
        second_request_full,
    )
    assert second_request["omitted_prefix_chars"] > 0
    assert second_request["content"] == second_request_full[second_request["omitted_prefix_chars"] :]
    first_response = json.dumps(
        llm._json_safe(provider.logger._serialize_response(responses[0])),
        ensure_ascii=False,
        sort_keys=True,
    )
    second_response_full = json.dumps(
        llm._json_safe(provider.logger._serialize_response(responses[1])),
        ensure_ascii=False,
        sort_keys=True,
    )
    second_response = second_record["response"]
    assert second_response["omitted_prefix_chars"] == llm._shared_prefix_length(
        first_response,
        second_response_full,
    )
    assert second_response["content"] == second_response_full[second_response["omitted_prefix_chars"] :]
