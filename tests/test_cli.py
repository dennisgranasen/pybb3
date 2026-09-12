from types import SimpleNamespace

from bb3 import cli


class FakeReplay:
    def __init__(self):
        self.redacted = None
        self.redact_calls = 0
        self.saved = []

    def redact_ip_addresses(self):
        self.redact_calls += 1
        if self.redacted is None:
            self.redacted = FakeReplay()
        return self.redacted

    def save(self, path):
        self.saved.append(path)


class FakeClient:
    def __init__(self, replay):
        self.replay = replay
        self.downloaded = []
        self.closed = False

    def download_replay(self, game_id):
        self.downloaded.append(game_id)
        return self.replay

    def close(self):
        self.closed = True


def _args(*, keep_ip_addresses):
    return SimpleNamespace(
        game_id="game-1",
        output="replay.bbr",
        keep_ip_addresses=keep_ip_addresses,
    )


def test_cmd_replay_redacts_by_default(monkeypatch, capsys):
    replay = FakeReplay()
    client = FakeClient(replay)
    monkeypatch.setattr(cli, "authenticated_client", lambda _args: client)

    assert cli.cmd_replay(_args(keep_ip_addresses=False)) == 0

    assert client.downloaded == ["game-1"]
    assert replay.redact_calls == 1
    assert replay.saved == []
    assert replay.redacted is not None
    assert replay.redacted.saved == ["replay.bbr"]
    assert client.closed is True
    assert capsys.readouterr().out == "replay.bbr\n"


def test_cmd_replay_keep_ip_addresses_saves_original(monkeypatch, capsys):
    replay = FakeReplay()
    client = FakeClient(replay)
    monkeypatch.setattr(cli, "authenticated_client", lambda _args: client)

    assert cli.cmd_replay(_args(keep_ip_addresses=True)) == 0

    assert client.downloaded == ["game-1"]
    assert replay.redact_calls == 0
    assert replay.saved == ["replay.bbr"]
    assert replay.redacted is None
    assert client.closed is True
    assert capsys.readouterr().out == "replay.bbr\n"
