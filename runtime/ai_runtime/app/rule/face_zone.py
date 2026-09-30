"""Presence-only trigger for a clearly designated, voluntary entrance scan position."""

from uuid import uuid4


class FaceZoneTrigger:
    def __init__(self):
        self.state = "WAIT_CLEAR"
        self.since = None
        self.encounter_id = None
        self.triggered_at = None

    def observe(self, now: int, occupied: bool, ready: bool):
        if self.state in {"TRIGGERED", "SCANNING"}:
            if self.state == "TRIGGERED" and now - self.triggered_at > 20000:
                self.finish()
            return
        if self.state == "WAIT_CLEAR":
            self.since = (self.since if self.since is not None else now) if not occupied else None
            if self.since is not None and now - self.since >= 1000:
                self.state, self.since = "READY", None
            return
        if not ready:
            self.state, self.since = "READY", None
            return
        self.state = "POSITIONING"
        self.since = now if self.since is None else self.since
        if now - self.since >= 1000:
            self.state = "TRIGGERED"
            self.encounter_id, self.triggered_at = str(uuid4()), now

    def acknowledge(self, encounter_id: str, completed: bool):
        if encounter_id != self.encounter_id:
            return
        if completed:
            self.finish()
        elif self.state == "TRIGGERED":
            self.state = "SCANNING"

    def finish(self):
        self.state, self.since = "WAIT_CLEAR", None
        self.encounter_id, self.triggered_at = None, None
