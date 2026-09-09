"""Unprivileged client for the joulectrl helper daemon (Agent A owns).

core/controller_client.py and any app code talk to the root helper through
this thin client: JSON-lines over /run/joulectrl-helper.sock.
"""

from __future__ import annotations

import json
import os
import socket

SOCKET_PATH = "/run/joulectrl-helper.sock"


class HelperClient:
    def __init__(self, socket_path: str = SOCKET_PATH, timeout: float = 10.0):
        self.socket_path = socket_path
        self.timeout = timeout

    def _call(self, op: str, args: dict | None = None) -> dict:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self.socket_path)
        try:
            with s.makefile("rw") as f:
                f.write(json.dumps({"op": op, "args": args or {}}) + "\n")
                f.flush()
                return json.loads(f.readline())
        finally:
            s.close()

    def begin_session(self, uid: int = None, pid: int = None) -> dict:
        return self._call("begin_session", {
            "uid": uid if uid is not None else os.getuid(),
            "pid": pid if pid is not None else os.getpid(),
        })

    def read_energy(self) -> dict:
        return self._call("read_energy")

    def apply_configuration(self, control: dict) -> dict:
        return self._call("apply_configuration", {"control": control})

    def heartbeat(self) -> dict:
        return self._call("heartbeat")

    def restore(self) -> dict:
        return self._call("restore")

    def end_session(self) -> dict:
        return self._call("end_session")


if __name__ == "__main__":
    import sys

    op = sys.argv[1] if len(sys.argv) > 1 else "read_energy"
    c = HelperClient()
    fn = {"read_energy": c.read_energy, "restore": c.restore,
          "begin_session": c.begin_session, "end_session": c.end_session,
          "heartbeat": c.heartbeat}.get(op)
    if fn is None:
        print(f"ops: {sorted(fn)}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(fn()))
