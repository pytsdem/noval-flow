from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from novel_flow.storage.sqlite_store import SQLiteStore

_bus_var: ContextVar[EventBus | None] = ContextVar("_bus_var", default=None)


class RunCancelledError(RuntimeError):
    """Raised when a running pipeline is cancelled by the user."""


@dataclass
class PipelineEvent:
    run_id: str
    event_type: str
    agent: str
    title: str
    payload: dict[str, Any]
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: int = 0


class EventBus:
    def __init__(self, run_id: str, store: SQLiteStore | None = None, cancel_event: Any | None = None) -> None:
        self.run_id = run_id
        self._store = store
        self._token: Token[EventBus | None] | None = None
        self._cancel_event = cancel_event

    def emit(self, event_type: str, agent: str = "", title: str = "", **payload: Any) -> None:
        if self.cancel_requested:
            return
        event = PipelineEvent(
            run_id=self.run_id,
            event_type=event_type,
            agent=agent,
            title=title,
            payload=payload,
        )
        if self._store is not None:
            self._store.save_event(event)

    @property
    def cancel_requested(self) -> bool:
        return bool(self._cancel_event and self._cancel_event.is_set())

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested:
            raise RunCancelledError(f"Run {self.run_id} cancelled.")

    def __enter__(self) -> EventBus:
        self._token = _bus_var.set(self)
        return self

    def __exit__(self, *_: object) -> None:
        if self._token is not None:
            _bus_var.reset(self._token)


def get_bus() -> EventBus | None:
    return _bus_var.get()


def emit(event_type: str, agent: str = "", title: str = "", **payload: Any) -> None:
    bus = get_bus()
    if bus is not None:
        bus.emit(event_type, agent=agent, title=title, **payload)


def check_cancelled() -> None:
    bus = get_bus()
    if bus is not None:
        bus.raise_if_cancelled()
