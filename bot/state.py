"""Remembers what has been posted (data/state.json, committed back by the workflow)."""
from __future__ import annotations

import json
from pathlib import Path

EMPTY = {"version": 1, "posts": [], "tool_history": [], "ali_used": []}


class State:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.data = json.loads(json.dumps(EMPTY))
        for k, v in EMPTY.items():
            self.data.setdefault(k, json.loads(json.dumps(v)))

    # ------------------------------------------------------------------
    @property
    def posts(self) -> list[dict]:
        return self.data["posts"]

    @property
    def published(self) -> list[dict]:
        return [p for p in self.posts if p.get("status") == "published"]

    def drop_unpublished(self) -> None:
        """Posts that were prepared but never went live are forgotten (their item is retried)."""
        self.data["posts"] = self.published

    def next_number(self) -> int:
        return max((p["number"] for p in self.published), default=0) + 1

    def used_keys(self) -> set[str]:
        return {p["key"] for p in self.published}

    def last_source(self) -> str | None:
        return self.published[-1]["source"] if self.published else None

    def published_on(self, date: str) -> dict | None:
        for p in self.published:
            if p.get("date") == date:
                return p
        return None

    def pending(self) -> dict | None:
        for p in reversed(self.posts):
            if p.get("status") in ("prepared", "failed"):
                return p
        return None

    # ------------------------------------------------------------------
    def remember_tool(self, tool_key: str, product_id: str) -> None:
        hist = [t for t in self.data["tool_history"] if t != tool_key]
        hist.append(tool_key)
        self.data["tool_history"] = hist
        if product_id and product_id not in self.data["ali_used"]:
            self.data["ali_used"].append(product_id)

    def tool_order(self, tools: list[str]) -> list[str]:
        """Least recently used tool type first."""
        hist = self.data["tool_history"]
        return sorted(tools, key=lambda t: hist.index(t) if t in hist else -1)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
