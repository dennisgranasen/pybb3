from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import TextIO


@dataclass(slots=True)
class SteamTicket:
    steam_id: str
    auth_token: str


class SteamAuthProcess:
    """Keep the SteamKit helper alive while the BB3 ticket is in use."""

    def __init__(self, helper: str):
        self.helper = helper
        self.process: subprocess.Popen[str] | None = None
        self.ticket: SteamTicket | None = None

    def start(self) -> SteamTicket:
        if self.process is not None:
            raise RuntimeError("Steam helper is already running")

        self.process = subprocess.Popen(
            [self.helper, "ticket"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
        )

        if self.process.stdout is None:
            raise RuntimeError("Steam helper stdout is unavailable")

        line = self.process.stdout.readline()
        if not line:
            self.process.wait()
            raise RuntimeError(
                "Steam helper exited before returning a ticket "
                f"(exit code {self.process.returncode})"
            )

        data = json.loads(line)
        self.ticket = SteamTicket(
            steam_id=str(data["steamId"]),
            auth_token=str(data["authToken"]),
        )
        return self.ticket

    def close(self) -> None:
        process = self.process
        self.process = None

        if process is None or process.poll() is not None:
            return

        try:
            if process.stdin is not None:
                process.stdin.write("\n")
                process.stdin.flush()
            process.wait(timeout=10)
        except Exception:
            process.kill()
            process.wait()

    def __enter__(self) -> SteamTicket:
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
