from __future__ import annotations

from typing import Any

from ..config import AppConfig
from ..llm import AnthropicProvider, extract_text, iter_tool_uses, normalize_content_blocks
from .files import run_bash, run_edit, run_read, run_write


class SubagentRunner:
    def __init__(self, config: AppConfig, provider: AnthropicProvider):
        self.config = config
        self.provider = provider

    def run(self, prompt: str, agent_type: str = "Explore") -> str:
        tools = [
            {
                "name": "bash",
                "description": "Run command.",
                "input_schema": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
            {
                "name": "read_file",
                "description": "Read file.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        ]
        if agent_type != "Explore":
            tools.extend(
                [
                    {
                        "name": "write_file",
                        "description": "Write file.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "content"],
                        },
                    },
                    {
                        "name": "edit_file",
                        "description": "Edit file.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "old_text": {"type": "string"},
                                "new_text": {"type": "string"},
                            },
                            "required": ["path", "old_text", "new_text"],
                        },
                    },
                ]
            )
        handlers = {
            "bash": lambda block: run_bash(self.config, block["input"]["command"]),
            "read_file": lambda block: run_read(self.config, block["input"]["path"]),
            "write_file": lambda block: run_write(
                self.config, block["input"]["path"], block["input"]["content"]
            ),
            "edit_file": lambda block: run_edit(
                self.config,
                block["input"]["path"],
                block["input"]["old_text"],
                block["input"]["new_text"],
            ),
        }
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        response = None
        for _ in range(30):
            response = self.provider.create_message(
                system=None,
                messages=messages,
                tools=tools,
                max_tokens=8000,
            )
            assistant_content = normalize_content_blocks(getattr(response, "content", []))
            messages.append({"role": "assistant", "content": assistant_content})
            if getattr(response, "stop_reason", None) != "tool_use":
                break
            results = []
            for block in iter_tool_uses(assistant_content):
                output = handlers.get(block["name"], lambda _: "Unknown tool")(block)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": str(output)[: self.config.max_tool_output_chars],
                    }
                )
            messages.append({"role": "user", "content": results})
        if response is None:
            return "(subagent failed)"
        return extract_text(getattr(response, "content", [])) or "(no summary)"
