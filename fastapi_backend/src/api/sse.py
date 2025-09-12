from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, DefaultDict, Dict, List
from collections import defaultdict


class SSEManager:
    """Simple in-memory SSE manager for per-event streams.

    Manages subscriber queues for each event_id. On broadcast, it sends a JSON-serializable
    payload to all subscribers for that event.
    """

    def __init__(self) -> None:
        # Map event_id to list of subscriber queues
        self._subscribers: DefaultDict[int, List[asyncio.Queue[str]]] = defaultdict(list)
        # Lock to protect subscriber list modifications
        self._lock = asyncio.Lock()

    async def subscribe(self, event_id: int) -> asyncio.Queue[str]:
        """Register a new subscriber for an event and return its message queue."""
        queue: asyncio.Queue[str] = asyncio.Queue()
        async with self._lock:
            self._subscribers[event_id].append(queue)
        return queue

    async def unsubscribe(self, event_id: int, queue: asyncio.Queue[str]) -> None:
        """Remove a subscriber's queue from the event list."""
        async with self._lock:
            if event_id in self._subscribers and queue in self._subscribers[event_id]:
                self._subscribers[event_id].remove(queue)
                if not self._subscribers[event_id]:
                    # Cleanup empty list to avoid growth of keys
                    self._subscribers.pop(event_id, None)

    async def broadcast(self, event_id: int, data: Dict[str, Any]) -> None:
        """Broadcast a JSON message to all subscribers of the given event_id."""
        message = f"data: {json.dumps(data)}\n\n"
        async with self._lock:
            queues = list(self._subscribers.get(event_id, []))
        # Put message into each subscriber queue non-blocking
        for q in queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                # If queue is full, drop the message for that subscriber to avoid blocking
                pass

    async def event_stream(self, event_id: int) -> AsyncGenerator[str, None]:
        """Async generator that yields SSE-formatted data strings for a subscriber."""
        queue = await self.subscribe(event_id)
        # Send initial comment to keep connection alive quickly
        try:
            # A first ping to ensure immediate response
            yield ": connected\n\n"
            while True:
                msg = await queue.get()
                yield msg
        finally:
            await self.unsubscribe(event_id, queue)


# Singleton instance used by the app
sse_manager = SSEManager()
