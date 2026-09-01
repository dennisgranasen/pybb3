from __future__ import annotations

import os

import pytest

from bb3 import BB3Client


pytestmark = pytest.mark.live


def require_opt_in(variable: str) -> None:
    if os.environ.get(variable) != "1":
        pytest.skip(f"set {variable}=1 to run this test")


def test_live_login():
    require_opt_in("PYBB3_RUN_LIVE_TESTS")

    with BB3Client.from_steam() as client:
        root = client.login()

    assert root.tag == "ResponseLogin"


@pytest.mark.destructive
def test_live_create_team():
    require_opt_in("PYBB3_RUN_LIVE_TESTS")
    require_opt_in("PYBB3_ALLOW_DESTRUCTIVE_TESTS")

    with BB3Client.from_steam() as client:
        client.login()
        team_id = client.create_team(name="pybb3 Test", race_id=2)

    assert team_id
