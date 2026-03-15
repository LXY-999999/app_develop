from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

AsyncToolCallable = Callable[..., Awaitable[Any]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    handler: AsyncToolCallable
    source: str = "local"


@dataclass(slots=True)
class ToolCallRecord:
    name: str
    kwargs: dict[str, Any]
    source: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""
    ok: bool = False
    result_preview: str = ""
    error: str = ""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._history: list[ToolCallRecord] = []

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def history(self) -> list[ToolCallRecord]:
        return list(self._history)

    async def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        spec = self._tools[name]
        record = ToolCallRecord(name=name, kwargs=kwargs, source=spec.source)
        self._history.append(record)
        try:
            result = await spec.handler(**kwargs)
            record.ok = True
            record.result_preview = repr(result)[:500]
            return result
        except Exception as exc:
            record.error = str(exc)
            raise
        finally:
            record.finished_at = datetime.now(timezone.utc).isoformat()

