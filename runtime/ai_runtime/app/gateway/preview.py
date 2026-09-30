"""Gateway signaling reuses the same WebRTC manager and camera media owner as platform preview."""

from ai_runtime.app.stream.webrtc import WebRtcOfferRequest


class GatewayPreview:
    def __init__(self, gateway, manager):
        self.gateway = gateway
        self.manager = manager
        self.sessions: dict[str, int] = {}

    async def invoke(self, action: str, payload: dict):
        self.sessions = {
            key: task for key, task in self.sessions.items() if self.manager.has_session(key)
        }
        task_id = int(payload["taskId"])
        document = self.gateway.store.get(task_id)
        if document is None:
            raise KeyError(task_id)
        if action == "preview.open":
            # The browser supplies only a task identity and SDP, never a camera credential or URL.
            config = document["config"]
            result = await self.manager.create_session(
                WebRtcOfferRequest(
                    cameraId=config["cameraId"],
                    sourceUrl=config["sourceUrl"],
                    offerSdp=payload["offerSdp"],
                    offerType=payload.get("offerType", "offer"),
                )
            )
            self.sessions[result.session_id] = task_id
            return result.model_dump(mode="json", by_alias=True)
        session_id = str(payload["sessionId"])
        if self.sessions.get(session_id) != task_id:
            raise KeyError(session_id)
        if action == "preview.close":
            await self.manager.release_session(session_id)
            self.sessions.pop(session_id, None)
            return {"released": True}
        try:
            result = await self.manager.get_session(session_id)
        except KeyError:
            self.sessions.pop(session_id, None)
            raise
        if action == "preview.status":
            return result.model_dump(mode="json", by_alias=True)
        if action == "preview.frames":
            frames = []
            for item in self.gateway.store.all():
                if (
                    not item["enabled"]
                    or item["config"]["cameraId"] != document["config"]["cameraId"]
                ):
                    continue
                frame = self.gateway.tasks.latest_overlay(item["config"]["taskId"])
                if frame is not None:
                    frames.append(
                        {
                            **frame.model_dump(
                                mode="json", by_alias=True, exclude={"image_base64"}
                            ),
                            "sessionId": session_id,
                        }
                    )
            return frames
        if action == "preview.frame":
            frame = self.gateway.tasks.latest_overlay(task_id)
            if not document["enabled"] or frame is None:
                return None
            return {
                **frame.model_dump(mode="json", by_alias=True, exclude={"image_base64"}),
                "sessionId": session_id,
            }
        raise ValueError("unsupported preview operation")
