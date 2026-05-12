"""Background task orchestration with concurrency guard, SSE event queue, and report storage."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class TaskManager:
    """Manages simulation lifecycle: concurrency guard, SSE emission, and report persistence."""

    def __init__(self):
        self._running: bool = False
        self._current_sim_id: str | None = None
        self._lock = threading.Lock()
        self._events: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._reports: dict[str, dict[str, str]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- concurrency guard --

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def current_sim_id(self) -> str | None:
        with self._lock:
            return self._current_sim_id

    def acquire(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            return True

    def release(self) -> None:
        with self._lock:
            self._running = False
            self._current_sim_id = None

    def reset(self) -> None:
        with self._lock:
            self._running = False
            self._current_sim_id = None
            self._events.clear()
            self._reports.clear()

    # -- event emission --

    def init_sim(self) -> str:
        sim_id = uuid.uuid4().hex[:12]
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self._current_sim_id = sim_id
        self._events[sim_id] = asyncio.Queue()
        return sim_id

    def emit_event(self, sim_id: str, event: str, data: dict[str, Any]) -> None:
        queue = self._events.get(sim_id)
        if queue is None:
            logger.warning("emit_event for unknown sim_id: %s", sim_id)
            return
        payload = {"event": event, "data": data}
        try:
            queue.put_nowait(payload)
        except Exception:
            logger.exception("Failed to emit event '%s' for sim_id=%s", event, sim_id)

    def get_queue(self, sim_id: str) -> asyncio.Queue | None:
        return self._events.get(sim_id)

    def has_sim(self, sim_id: str) -> bool:
        return sim_id in self._events

    # -- report persistence --

    def set_report(self, sim_id: str, report: dict[str, str]) -> None:
        self._reports[sim_id] = report

    def get_report(self, sim_id: str) -> dict[str, str] | None:
        return self._reports.get(sim_id)


task_manager = TaskManager()
