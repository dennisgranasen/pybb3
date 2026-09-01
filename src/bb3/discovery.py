from __future__ import annotations

import http.client
from dataclasses import dataclass
from urllib.parse import urlparse

from .constants import DEFAULT_BOOTSTRAP_HOST, DEFAULT_BOOTSTRAP_PORT


class BB3DiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BB3Endpoint:
    host: str
    port: int


def discover_bb3_endpoint(
    client_version: str,
    *,
    bootstrap_host: str = DEFAULT_BOOTSTRAP_HOST,
    bootstrap_port: int = DEFAULT_BOOTSTRAP_PORT,
    timeout: float = 10.0,
    user_agent: str = "BB3 headless client",
) -> BB3Endpoint:
    """Ask Cyanide's bootstrap service which BB3 application server to use."""
    conn = http.client.HTTPConnection(
        bootstrap_host,
        bootstrap_port,
        timeout=timeout,
    )
    try:
        conn.request(
            "GET",
            f"/lobby/{client_version}",
            headers={"Accept": "*/*", "User-Agent": user_agent},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8", errors="strict").strip()
    finally:
        conn.close()

    if response.status != 200:
        raise BB3DiscoveryError(
            f"BB3 bootstrap failed: HTTP {response.status} {response.reason}: {body!r}"
        )

    parsed = urlparse(body)
    if parsed.scheme != "tcp" or not parsed.hostname or parsed.port is None:
        raise BB3DiscoveryError(f"Unexpected BB3 bootstrap response: {body!r}")

    return BB3Endpoint(parsed.hostname, parsed.port)
