"""WebSocket hub (SRS §12.7). Topics: branch:{id}, station:{branch}:{code}, user:{id}, tables:{branch}.

Events are queued on the DB session and published only after the transaction commits.
With REDIS_URL set, events go through Redis pub/sub so several API workers share them.
"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from sqlalchemy import event
from sqlalchemy.orm import Session

log = logging.getLogger("rms.realtime")


class Hub:
    def __init__(self) -> None:
        self.subscribers: dict[str, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.redis = None

    async def start(self, redis_url: str) -> None:
        self.loop = asyncio.get_running_loop()
        if redis_url:
            import redis.asyncio as aioredis

            self.redis = aioredis.from_url(redis_url)
            asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.psubscribe("rms:*")
        async for message in pubsub.listen():
            if message.get("type") == "pmessage":
                data = json.loads(message["data"])
                await self._deliver(data["topic"], data)

    def subscribe(self, ws: WebSocket, topic: str) -> None:
        self.subscribers[topic].add(ws)

    def unsubscribe_all(self, ws: WebSocket) -> None:
        for subs in self.subscribers.values():
            subs.discard(ws)

    async def _deliver(self, topic: str, message: dict) -> None:
        for ws in list(self.subscribers.get(topic, ())):
            try:
                await ws.send_json(message)
            except Exception:
                self.subscribers[topic].discard(ws)

    def publish(self, topic: str, event_type: str, payload: dict[str, Any]) -> None:
        message = {"topic": topic, "type": event_type, "data": payload}
        if self.loop is None:
            return
        if self.redis is not None:
            asyncio.run_coroutine_threadsafe(self.redis.publish(f"rms:{topic}", json.dumps(message, default=str)), self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self._deliver(topic, json.loads(json.dumps(message, default=str))), self.loop)


hub = Hub()


def emit(db: Session, topic: str, event_type: str, payload: dict[str, Any]) -> None:
    """Queue an event; it is published only if the transaction commits."""
    db.info.setdefault("pending_events", []).append((topic, event_type, payload))


@event.listens_for(Session, "after_commit")
def _flush_events(session: Session) -> None:
    for topic, event_type, payload in session.info.pop("pending_events", []):
        try:
            hub.publish(topic, event_type, payload)
        except Exception:  # never fail a committed request because of a socket
            log.exception("publish failed")


@event.listens_for(Session, "after_rollback")
def _drop_events(session: Session) -> None:
    session.info.pop("pending_events", None)
