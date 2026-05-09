"""Background task orchestration with concurrency guard and SSE event queue."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class TaskManager:
    """Manages simulation lifecycle: concurrency guard and SSE event emission.

    Uses an in-memory event queue keyed by sim_id. SSE endpoints drain
    their queue as Server-Sent Events.
    """

    def __init__(self):
        self._running: bool = False
        self._lock = threading.Lock()
        self._events: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    # -- concurrency guard --

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def acquire(self) -> bool:
        """Try to acquire the simulation lock. Returns False if already running."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            return True

    def release(self) -> None:
        with self._lock:
            self._running = False

    def reset(self) -> None:
        """Reset all state (for tests)."""
        with self._lock:
            self._running = False
            self._events.clear()

    # -- event emission --

    def init_sim(self) -> str:
        """Create a new simulation slot and return its ID."""
        sim_id = uuid.uuid4().hex[:12]
        self._events[sim_id] = asyncio.Queue()
        return sim_id

    def emit_event(self, sim_id: str, event: str, data: dict[str, Any]) -> None:
        """Push an SSE event onto the queue for the given simulation."""
        queue = self._events.get(sim_id)
        if queue is None:
            logger.warning("emit_event for unknown sim_id: %s", sim_id)
            return
        queue.put_nowait({"event": event, "data": data})

    def get_queue(self, sim_id: str) -> asyncio.Queue | None:
        return self._events.get(sim_id)

    def has_sim(self, sim_id: str) -> bool:
        return sim_id in self._events


task_manager = TaskManager()
