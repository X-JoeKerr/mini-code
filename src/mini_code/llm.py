from __future__ import annotations

import os
from typing import Any, Iterable

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - fallback for bare environments
    Anthropic = None  # type: ignore[assignment]

from .config import AppConfig


class AnthropicProvider:
    """Thin wrapper around the Anthropic client."""

    def __init__(self, config: AppConfig):
        if config.anthropic_base_url:
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        if Anthropic is None:
            raise RuntimeError("anthropic package is not installed")
        self.config = config
        self.client = Anthropic(base_url=config.anthropic_base_url)

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
        return self.client.messages.create(**payload)


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
