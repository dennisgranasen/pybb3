from __future__ import annotations

import io
import json

from bb3.client import BB3Client
from bb3.steam import (
    SteamAuthProcess,
    SteamAuthState,
    SteamTicket,
    resolve_credentials,
)


def test_username_from_environment(tmp_path):
    assert resolve_credentials(environ={"STEAM_USERNAME": "env-user"},
                               dotenv_path=tmp_path / ".env") == ("env-user", None)


def test_username_from_dotenv(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("STEAM_USERNAME=dotenv-user\n", encoding="utf-8")
    assert resolve_credentials(environ={}, dotenv_path=dotenv) == ("dotenv-user", None)


def test_interactive_username_fallback(tmp_path):
    result = resolve_credentials(environ={}, dotenv_path=tmp_path / ".env",
                                 input_fn=lambda _: "prompt-user")
    assert result == ("prompt-user", None)


def test_password_from_environment(tmp_path):
    result = resolve_credentials(environ={"STEAM_USERNAME": "u",
                                          "STEAM_PASSWORD": "secret"},
                                 dotenv_path=tmp_path / ".env")
    assert result == ("u", "secret")


def test_environment_overrides_dotenv(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("STEAM_USERNAME=file-user\nSTEAM_PASSWORD=file-pass\n",
                      encoding="utf-8")
    result = resolve_credentials(environ={"STEAM_USERNAME": "env-user",
                                          "STEAM_PASSWORD": "env-pass"},
                                 dotenv_path=dotenv)
    assert result == ("env-user", "env-pass")


def test_secure_password_prompt_fallback(monkeypatch, tmp_path):
    auth = SteamAuthProcess("helper", cache_path=tmp_path / "cache", environ={})
    auth.password_fn = lambda _: "prompt-secret"
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs["env"])
        payload = {"username": "u", "refreshToken": "r", "guardData": None}
        return type("Result", (), {"stdout": json.dumps(payload)})()

    monkeypatch.setattr("bb3.steam.subprocess.run", fake_run)
    auth._bootstrap("u", None)
    assert seen["STEAM_PASSWORD"] == "prompt-secret"


def test_helper_process_cleanup(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    cache.write_text(json.dumps({"username": "u", "refreshToken": "r"}),
                     encoding="utf-8")

    class Process:
        stdout = io.StringIO('{"steamId":"1","authToken":"token"}\n')
        stdin = io.StringIO()
        returncode = None

        def poll(self): return None
        def wait(self, timeout=None): self.returncode = 0
        def kill(self): self.returncode = -9

    process = Process()
    monkeypatch.setattr("bb3.steam.subprocess.Popen", lambda *a, **k: process)
    auth = SteamAuthProcess("helper", cache_path=cache,
                            environ={"STEAM_USERNAME": "u"})
    assert auth.start().steam_id == "1"
    auth.close()
    assert process.stdin.getvalue() == "\n"
    assert auth.process is None


def test_secret_objects_have_redacted_repr():
    assert "token" not in repr(SteamTicket("1", "token"))
    assert "refresh" not in repr(SteamAuthState("u", "refresh"))


def test_client_cleans_up_helper_when_connect_fails(monkeypatch):
    class Auth:
        closed = False

        def start(self):
            return SteamTicket("1", "token")

        def close(self):
            self.closed = True

    auth = Auth()
    client = BB3Client(steam_auth=auth)
    monkeypatch.setattr(client, "connect", lambda: (_ for _ in ()).throw(OSError()))
    try:
        client.__enter__()
    except OSError:
        pass
    assert auth.closed
