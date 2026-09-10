from __future__ import annotations

import itertools
import os

import pytest

from bb3 import BB3Client
from bb3.replay import (
    documentation_ipv4_addresses,
    download_any_replay,
    extract_replay_ip_addresses,
)


pytestmark = pytest.mark.live


def test_live_downloaded_replay_contains_only_inserted_test_addresses(tmp_path):
    if os.environ.get("PYBB3_RUN_LIVE_TESTS") != "1":
        pytest.skip("set PYBB3_RUN_LIVE_TESTS=1 to run this test")

    with BB3Client.from_steam() as client:
        client.login()
        artifacts = download_any_replay(client, tmp_path)

    assert artifacts.replay_path.is_file()
    assert artifacts.json_path.is_file()
    addresses = extract_replay_ip_addresses(artifacts.replay_path.read_bytes())
    assert addresses, "The downloaded replay contained no IpAddress fields"
    allowed = set(itertools.islice(documentation_ipv4_addresses(), len(set(addresses))))
    assert set(addresses) == allowed
