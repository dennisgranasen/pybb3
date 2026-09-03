from __future__ import annotations

import io
import json

from bb3.client import BB3Client
from bb3.steam import (
    SteamAuthProcess,
    SteamAuthState,
    SteamTicket,
    SteamGuardChallenge,
    SteamWebAuthFlow,
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
        return type("Result", (), {"stdout": json.dumps(payload), "stderr": "",
                                    "returncode": 0})()

    monkeypatch.setattr("bb3.steam.subprocess.run", fake_run)
    auth._bootstrap("u", None)
    assert seen["STEAM_PASSWORD"] == "prompt-secret"


def test_bootstrap_accepts_json_after_dotnet_build_output(monkeypatch, tmp_path):
    payload = {"username": "u", "refreshToken": "r", "guardData": None}

    def fake_run(*args, **kwargs):
        return type("Result", (), {"stdout": f"Build succeeded.\n{json.dumps(payload)}\n",
                                    "stderr": "", "returncode": 0})()

    monkeypatch.setattr("bb3.steam.subprocess.run", fake_run)
    auth = SteamAuthProcess("helper", cache_path=tmp_path / "cache", environ={})
    assert auth._bootstrap("u", "secret").refresh_token == "r"


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


def test_ticket_accepts_json_after_dotnet_build_output(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    cache.write_text(json.dumps({"username": "u", "refreshToken": "r"}),
                     encoding="utf-8")

    class Process:
        stdout = io.StringIO('Build succeeded.\n{"steamId":"1","authToken":"token"}\n')
        stdin = io.StringIO()
        returncode = None

        def poll(self): return None
        def wait(self, timeout=None): self.returncode = 0
        def kill(self): self.returncode = -9

    monkeypatch.setattr("bb3.steam.subprocess.Popen", lambda *a, **k: Process())
    auth = SteamAuthProcess("helper", cache_path=cache,
                            environ={"STEAM_USERNAME": "u"})
    assert auth.start().steam_id == "1"


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


class WebAuthProcess:
    def __init__(self, events):
        self.stdout = io.StringIO("\n".join(json.dumps(event) for event in events) + "\n")
        self.stderr = io.StringIO()
        self.stdin = io.StringIO()
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def test_web_auth_flow_returns_challenge_then_isolated_auth_state(monkeypatch):
    process = WebAuthProcess([
        {"eventType": "steam_guard_required", "method": "email_code",
         "email": "d***@example.com", "previousCodeWasIncorrect": False},
        {"eventType": "auth_state", "username": "dennis",
         "refreshToken": "refresh", "guardData": "guard"},
    ])
    seen = {}

    def popen(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        return process

    monkeypatch.setattr("bb3.steam.subprocess.Popen", popen)
    flow = SteamWebAuthFlow("helper", environ={"SAFE": "value"})

    challenge = flow.start("dennis", "password")
    assert challenge == SteamGuardChallenge("email_code", "d***@example.com", False)
    assert seen["command"] == ["helper", "bootstrap-web"]
    assert "STEAM_USERNAME" not in seen["env"]
    assert "STEAM_PASSWORD" not in seen["env"]

    state = flow.submit_code(" ABC12 ")
    assert state == SteamAuthState("dennis", "refresh", "guard")
    requests = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert requests == [
        {"username": "dennis", "password": "password"},
        {"code": "ABC12"},
    ]
    assert flow.process is None


def test_web_auth_flows_do_not_share_process_or_challenge(monkeypatch):
    processes = iter([
        WebAuthProcess([{"eventType": "steam_guard_required", "method": "device_code"}]),
        WebAuthProcess([{"eventType": "steam_guard_required", "method": "device_confirmation"}]),
    ])
    monkeypatch.setattr("bb3.steam.subprocess.Popen", lambda *args, **kwargs: next(processes))

    first = SteamWebAuthFlow("helper", environ={})
    second = SteamWebAuthFlow("helper", environ={})
    assert first.start("first", "secret").method == "device_code"
    assert second.start("second", "secret").method == "device_confirmation"
    assert first.process is not second.process
    assert first.challenge != second.challenge
    first.close()
    second.close()


def test_auth_process_from_state_uses_no_shared_cache(monkeypatch, tmp_path):
    process = WebAuthProcess([{"steamId": "1", "authToken": "ticket"}])
    seen = {}

    def popen(command, **kwargs):
        seen["env"] = kwargs["env"]
        return process

    monkeypatch.setattr("bb3.steam.subprocess.Popen", popen)
    state = SteamAuthState("user", "refresh", "guard")
    auth = SteamAuthProcess.from_state(state, "helper", environ={})
    ticket = auth.start()

    assert ticket == SteamTicket("1", "ticket")
    assert seen["env"]["STEAM_USERNAME"] == "user"
    assert seen["env"]["STEAM_REFRESH_TOKEN"] == "refresh"
    assert seen["env"]["STEAM_GUARD_DATA"] == "guard"
    assert not (tmp_path / "cache").exists()
    auth.close()
