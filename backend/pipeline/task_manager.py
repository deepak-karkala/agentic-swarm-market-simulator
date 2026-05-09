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

    threading.Lock protects _running and _current_sim_id (accessed from both
    async event loop and background pipeline thread).  asyncio.Queue is only
    safe within the event loop that created it — emit_event bridges the
    background thread via loop.call_soon_threadsafe().

    Background pipeline (Task 6.1) runs in a thread spawned by FastAPI's
    BackgroundTasks.  That thread calls emit_event, which must push events
    into the SSE queue safely across the thread boundary.
    """

    def __init__(self):
        self._running: bool = False
        self._current_sim_id: str | None = None
        self._lock = threading.Lock()
        self._events: dict[str, asyncio.Queue[dict[str, Any]]] = {}
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
        """Try to acquire the simulation lock. Returns False if already running."""
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
        """Reset all state (for tests)."""
        with self._lock:
            self._running = False
            self._current_sim_id = None
            self._events.clear()

    # -- event emission --

    def init_sim(self) -> str:
        """Create a new simulation slot and return its ID."""
        sim_id = uuid.uuid4().hex[:12]
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self._current_sim_id = sim_id
        self._events[sim_id] = asyncio.Queue()
        return sim_id

    def emit_event(self, sim_id: str, event: str, data: dict[str, Any]) -> None:
        """Push an SSE event thread-safely onto the queue for the given simulation.

        Safe to call from any thread. When called from the background
        pipeline thread, bridges into the event loop via
        loop.call_soon_threadsafe().
        """
        queue = self._events.get(sim_id)
        if queue is None:
            logger.warning("emit_event for unknown sim_id: %s", sim_id)
            return
        payload = {"event": event, "data": data}
        loop = self._loop
        if loop is not None and loop is not asyncio.get_event_loop():
            loop.call_soon_threadsafe(queue.put_nowait, payload)
        else:
            queue.put_nowait(payload)

    def get_queue(self, sim_id: str) -> asyncio.Queue | None:
        return self._events.get(sim_id)

    def has_sim(self, sim_id: str) -> bool:
        return sim_id in self._events


task_manager = TaskManager()
