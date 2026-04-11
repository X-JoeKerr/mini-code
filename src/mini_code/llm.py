from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - fallback for bare environments
    Anthropic = None  # type: ignore[assignment]

from .config import AppConfig


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


class LLMInteractionLogger:
    """Append structured LLM request/response records to a session JSONL file."""

    def __init__(self, config: AppConfig):
        self.session_id = config.session_id
        self.path = config.llm_session_log_path
        self._lock = threading.Lock()
        self._previous_serialized: dict[str, str | None] = {
            "request": None,
            "response": None,
            "error": None,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        request: dict[str, Any],
        response: Any = None,
        error: Exception | None = None,
        duration_ms: int | None = None,
    ) -> None:
        safe_request = _json_safe(request)
        safe_response = self._serialize_response(response) if response is not None else None
        safe_error = self._serialize_error(error)
        record = {
            "event": "llm_interaction",
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": self.session_id,
            "request": self._compact_section("request", safe_request),
            "response": self._compact_section("response", safe_response),
            "error": self._compact_section("error", safe_error),
            "duration_ms": duration_ms,
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _compact_section(self, section: str, payload: Any) -> dict[str, Any] | None:
        if payload is None:
            self._previous_serialized[section] = None
            return None
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        previous = self._previous_serialized.get(section)
        omitted_prefix_chars = _shared_prefix_length(previous, serialized) if previous else 0
        self._previous_serialized[section] = serialized
        return {
            "encoding": "json",
            "omitted_prefix_chars": omitted_prefix_chars,
            "content": serialized[omitted_prefix_chars:],
        }

    def _serialize_response(self, response: Any) -> dict[str, Any]:
        payload = {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", None),
            "role": getattr(response, "role", None),
            "type": getattr(response, "type", None),
            "stop_reason": getattr(response, "stop_reason", None),
            "stop_sequence": getattr(response, "stop_sequence", None),
            "content": normalize_content_blocks(getattr(response, "content", [])),
        }
        usage = getattr(response, "usage", None)
        if usage is not None:
            payload["usage"] = _json_safe(usage)
        return _json_safe(payload)

    @staticmethod
    def _serialize_error(error: Exception | None) -> dict[str, str] | None:
        if error is None:
            return None
        return {"type": error.__class__.__name__, "message": str(error)}


class AnthropicProvider:
    """Thin wrapper around the Anthropic client."""

    def __init__(self, config: AppConfig):
        if config.anthropic_base_url:
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        if Anthropic is None:
            raise RuntimeError("anthropic package is not installed")
        self.config = config
        self.client = Anthropic(base_url=config.anthropic_base_url)
        self.logger = LLMInteractionLogger(config)

    def create_message(
        self,
        system: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
    ) -> Any:
        payload: dict[str, Any] = {
            "model": self.config.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if system is not None:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        start = time.perf_counter()
        try:
            response = self.client.messages.create(**payload)
        except Exception as exc:
            self.logger.log(
                request=payload,
                error=exc,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
            raise
        self.logger.log(
            request=payload,
            response=response,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
        return response


def normalize_content_blocks(content: Iterable[Any] | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if content is None:
        return blocks
    for block in content:
        if isinstance(block, dict):
            blocks.append(dict(block))
            continue
        payload: dict[str, Any] = {"type": getattr(block, "type", "text")}
        for attr in ("id", "name", "text", "input"):
            if hasattr(block, attr):
                payload[attr] = getattr(block, attr)
        blocks.append(payload)
    return blocks


def iter_tool_uses(content: Iterable[Any] | None) -> list[dict[str, Any]]:
    return [block for block in normalize_content_blocks(content) if block.get("type") == "tool_use"]


def extract_text(content: Iterable[Any] | None) -> str:
    parts = []
    for block in normalize_content_blocks(content):
        if block.get("type") == "text" and "text" in block:
            parts.append(str(block["text"]))
    return "".join(parts)


def _shared_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index
