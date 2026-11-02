from __future__ import annotations

import asyncio

from channels_redis.pubsub import RedisPubSubChannelLayer
from django.conf import settings
import redis.asyncio


async def kill_idle_publish_connections(admin: redis.asyncio.Redis) -> int:
    # Redis closes idle non-pub/sub clients once the server timeout elapses;
    # killing the connection that last issued PUBLISH reproduces that without
    # changing server config.
    killed = 0
    for client in await admin.client_list(_type="normal"):
        if client["cmd"] == "publish":
            killed += await admin.client_kill_filter(_id=client["id"])
    return killed


async def send_after_close() -> None:
    config = settings.CHANNEL_LAYERS["default"]["CONFIG"]
    layer = RedisPubSubChannelLayer(**config)
    admin = redis.asyncio.Redis.from_url(config["hosts"][0]["address"])
    try:
        channel = await layer.new_channel()
        await layer.group_add("test_reconnect", channel)

        await layer.group_send("test_reconnect", {"type": "first"})
        message = await asyncio.wait_for(layer.receive(channel), timeout=5)
        assert message["type"] == "first"

        assert await kill_idle_publish_connections(admin) >= 1

        # Without a retry configured, this raises "Connection closed by server."
        await layer.group_send("test_reconnect", {"type": "second"})
        message = await asyncio.wait_for(layer.receive(channel), timeout=5)
        assert message["type"] == "second"
    finally:
        await layer.flush()
        await admin.aclose()


def test_send_after_close():
    asyncio.run(send_after_close())
