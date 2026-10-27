"""Append-only, hash-chained audit trail (in memory)."""

import hashlib
import json


class AuditLog:
    def __init__(self):
        self.events = []

    def record(self, actor, action, target, at):
        prev = self.events[-1]["hash"] if self.events else "0" * 64
        body = {"actor": actor, "action": action, "target": target, "at": at, "prev": prev}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        self.events.append({**body, "hash": digest})
