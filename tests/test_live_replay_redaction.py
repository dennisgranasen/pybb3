from __future__ import annotations

import itertools
import os

import pytest

from bb3 import BB3Client
from bb3.replay import documentation_ipv4_addresses, extract_replay_ip_addresses
from tools.download_any_replay import find_official_replay_game


pytestmark = pytest.mark.live


def test_live_downloaded_replay_contains_only_inserted_test_addresses(tmp_path):
    if os.environ.get("PYBB3_RUN_LIVE_TESTS") != "1":
        pytest.skip("set PYBB3_RUN_LIVE_TESTS=1 to run this test")

    with BB3Client.from_steam() as client:
        client.login()
        game = find_official_replay_game(
            client, search_size=25, progress=lambda _message: None
        )
        replay = client.download_replay(game.game_id)
        anonymous = replay.redact_ip_addresses()
        replay_xml = anonymous.xml_data
        bbr_path = anonymous.save(tmp_path / f"{game.game_id}.bbr")
        anonymous.save(tmp_path / f"{game.game_id}.xml")
        anonymous.save(tmp_path / f"{game.game_id}.json")

    assert bbr_path.is_file()
    assert (tmp_path / f"{game.game_id}.xml").is_file()
    assert (tmp_path / f"{game.game_id}.json").is_file()
    assert type(replay).from_bbr(bbr_path.read_text()).xml_data == replay_xml
    addresses = extract_replay_ip_addresses(replay_xml)
    assert addresses, "The downloaded replay contained no IpAddress fields"
    allowed = set(itertools.islice(documentation_ipv4_addresses(), len(set(addresses))))
    assert set(addresses) == allowed
