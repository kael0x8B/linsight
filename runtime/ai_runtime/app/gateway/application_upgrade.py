"""Local and platform callers share the installer, never gain its filesystem privileges."""

import asyncio

from edge_agent.app.upgrade.daemon import SOCKET, request


async def invoke(action: str, payload: dict) -> dict:
    action = action.removeprefix("app-upgrade.")
    if action == "status" and not SOCKET.exists():
        return {"supported": False, "message": "设备尚未完成应用升级器首次迁移"}
    return await asyncio.to_thread(request, action, payload)
