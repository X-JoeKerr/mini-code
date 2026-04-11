from __future__ import annotations

from ..models import TodoItem


class TodoManager:
    def __init__(self) -> None:
        self.items: list[TodoItem] = []

    def update(self, items: list[dict]) -> str:
        validated: list[TodoItem] = []
        in_progress = 0
        for index, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            active_form = str(
                item.get("active_form", item.get("activeForm", ""))
            ).strip()
            if not content:
                raise ValueError(f"Item {index}: content required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {index}: invalid status '{status}'")
            if not active_form:
                raise ValueError(f"Item {index}: active_form required")
            if status == "in_progress":
                in_progress += 1
            validated.append(TodoItem(content=content, status=status, active_form=active_form))
        if len(validated) > 20:
            raise ValueError("Max 20 todos")
        if in_progress > 1:
            raise ValueError("Only one in_progress allowed")
        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        lines: list[str] = []
        for item in self.items:
            marker = {
                "completed": "[x]",
                "in_progress": "[>]",
                "pending": "[ ]",
            }.get(item.status, "[?]")
            suffix = f" <- {item.active_form}" if item.status == "in_progress" else ""
            lines.append(f"{marker} {item.content}{suffix}")
        completed = sum(1 for item in self.items if item.status == "completed")
        lines.append(f"\n({completed}/{len(self.items)} completed)")
        return "\n".join(lines)

    def has_open_items(self) -> bool:
        return any(item.status != "completed" for item in self.items)
