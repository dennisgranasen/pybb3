from __future__ import annotations

from dataclasses import dataclass
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping, Sequence

from .config import dotenv_values, environment_value

DEFAULT_AUTH_CACHE = ".bb3-steam-auth.json"


@dataclass(slots=True, repr=False)
class SteamTicket:
    steam_id: str
    auth_token: str


@dataclass(slots=True, repr=False)
class SteamAuthState:
    username: str
    refresh_token: str
    guard_data: str | None = None


@dataclass(slots=True, frozen=True)
class SteamGuardChallenge:
    method: str
    email: str | None = None
    previous_code_was_incorrect: bool = False


def resolve_credentials(
    *, environ: Mapping[str, str] | None = None,
    dotenv_path: str | Path = ".env",
    input_fn: Callable[[str], str] = input,
) -> tuple[str, str | None]:
    dotenv = dotenv_values(dotenv_path)
    username = environment_value(
        "STEAM_USERNAME", environ=environ, dotenv=dotenv
    )
    password = environment_value(
        "STEAM_PASSWORD", environ=environ, dotenv=dotenv
    )
    if not username:
        username = input_fn("Steam account login name: ").strip()
    if not username:
        raise ValueError("Steam account login name is required")
    return username, password or None


def _default_helper_command() -> list[str]:
    configured = os.environ.get("BB3_STEAM_HELPER")
    if configured:
        return [configured]
    project = Path(__file__).resolve().parents[2] / "steam-helper" / "BB3SteamAuth.csproj"
    if project.is_file():
        return ["dotnet", "run", "--project", str(project), "--"]
    name = "BB3SteamAuth.exe" if sys.platform == "win32" else "BB3SteamAuth"
    return [name]


class SteamAuthProcess:
    """Acquire persistent Steam state and own the live ticket helper."""

    def __init__(self, helper: str | Sequence[str] | None = None, *,
                 cache_path: str | Path = DEFAULT_AUTH_CACHE,
                 dotenv_path: str | Path = ".env",
                 environ: Mapping[str, str] | None = None,
                 input_fn: Callable[[str], str] = input,
                 password_fn: Callable[[str], str] = getpass.getpass,
                 auth_state: SteamAuthState | None = None):
        self.command = (_default_helper_command() if helper is None else
                        [helper] if isinstance(helper, str) else list(helper))
        self.cache_path = Path(cache_path)
        self.dotenv_path = Path(dotenv_path)
        self.environ = os.environ if environ is None else environ
        self.input_fn = input_fn
        self.password_fn = password_fn
        self.auth_state = auth_state
        self.process: subprocess.Popen[str] | None = None
        self.ticket: SteamTicket | None = None

    @classmethod
    def from_state(
        cls,
        state: SteamAuthState,
        helper: str | Sequence[str] | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> "SteamAuthProcess":
        """Create a ticket owner from an externally managed Steam auth state.

        This does not read or write the shared CLI cache and is intended for
        services that keep one isolated auth state per signed-in user.
        """
        return cls(helper, environ=environ, auth_state=state)

    def _read_state(self, username: str) -> SteamAuthState | None:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if data.get("username") != username or not data.get("refreshToken"):
                return None
            return SteamAuthState(username, data["refreshToken"], data.get("guardData"))
        except (OSError, ValueError, TypeError):
            return None

    def _write_state(self, state: SteamAuthState) -> None:
        self.cache_path.write_text(json.dumps({"username": state.username,
                                               "refreshToken": state.refresh_token,
                                               "guardData": state.guard_data}), encoding="utf-8")
        try:
            self.cache_path.chmod(0o600)
        except OSError:
            pass

    def _bootstrap(self, username: str, password: str | None) -> SteamAuthState:
        password = password or self.password_fn("Steam password: ")
        child_env = dict(self.environ)
        child_env.update(STEAM_USERNAME=username, STEAM_PASSWORD=password)
        result = subprocess.run([*self.command, "bootstrap"], env=child_env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
            raise RuntimeError("Steam helper bootstrap failed "
                               f"(exit code {result.returncode}): {detail}")
        try:
            data = next(
                json.loads(line)
                for line in reversed(result.stdout.splitlines())
                if line.lstrip().startswith("{")
            )
        except (StopIteration, json.JSONDecodeError) as error:
            detail = result.stderr.strip() or result.stdout.strip() or "no output"
            raise RuntimeError(f"Steam helper bootstrap returned invalid JSON: {detail}") from error
        state = SteamAuthState(str(data["username"]), str(data["refreshToken"]),
                               data.get("guardData"))
        self._write_state(state)
        return state

    def start(self) -> SteamTicket:
        if self.process is not None:
            raise RuntimeError("Steam helper is already running")
        if self.auth_state is not None:
            state = self.auth_state
        else:
            username, password = resolve_credentials(environ=self.environ,
                                                     dotenv_path=self.dotenv_path,
                                                     input_fn=self.input_fn)
            state = self._read_state(username) or self._bootstrap(username, password)
        child_env = dict(self.environ)
        child_env.update(STEAM_USERNAME=state.username,
                         STEAM_REFRESH_TOKEN=state.refresh_token)
        if state.guard_data:
            child_env["STEAM_GUARD_DATA"] = state.guard_data
        try:
            self.process = subprocess.Popen([*self.command, "ticket"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
                env=child_env, text=True, bufsize=1)
            if self.process.stdout is None:
                raise RuntimeError("Steam helper stdout is unavailable")
            while True:
                line = self.process.stdout.readline()
                if not line:
                    self.process.wait()
                    raise RuntimeError("Steam helper exited before returning a ticket "
                                       f"(exit code {self.process.returncode})")
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            self.ticket = SteamTicket(str(data["steamId"]), str(data["authToken"]))
            return self.ticket
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        process, self.process = self.process, None
        self.ticket = None
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


class SteamWebAuthFlow:
    """Drive Steam Guard authentication across multiple web requests.

    One instance represents one pending login and must never be shared between
    users. The hosting service is responsible for owner binding, expiration,
    rate limiting and encrypted persistence of the returned auth state.
    """

    def __init__(
        self,
        helper: str | Sequence[str] | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ):
        self.command = (_default_helper_command() if helper is None else
                        [helper] if isinstance(helper, str) else list(helper))
        self.environ = os.environ if environ is None else environ
        self.process: subprocess.Popen[str] | None = None
        self.challenge: SteamGuardChallenge | None = None

    def start(self, username: str, password: str) -> SteamGuardChallenge | SteamAuthState:
        if self.process is not None:
            raise RuntimeError("Steam web authentication is already running")
        if not username.strip() or not password:
            raise ValueError("Steam username and password are required")
        self.process = subprocess.Popen(
            [*self.command, "bootstrap-web"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(self.environ),
            text=True,
            bufsize=1,
        )
        if self.process.stdin is None:
            self.close()
            raise RuntimeError("Steam helper stdin is unavailable")
        self.process.stdin.write(json.dumps({
            "username": username.strip(),
            "password": password,
        }) + "\n")
        self.process.stdin.flush()
        return self._read_event()

    def submit_code(self, code: str) -> SteamGuardChallenge | SteamAuthState:
        if not code.strip():
            raise ValueError("Steam Guard code is required")
        return self._respond({"code": code.strip()})

    def confirm_device(self, approved: bool = True) -> SteamGuardChallenge | SteamAuthState:
        return self._respond({"approved": approved})

    def _respond(self, response: dict[str, object]) -> SteamGuardChallenge | SteamAuthState:
        process = self._require_process()
        if self.challenge is None:
            raise RuntimeError("Steam authentication is not waiting for a challenge response")
        if process.stdin is None:
            raise RuntimeError("Steam helper stdin is unavailable")
        process.stdin.write(json.dumps(response) + "\n")
        process.stdin.flush()
        self.challenge = None
        return self._read_event()

    def _read_event(self) -> SteamGuardChallenge | SteamAuthState:
        process = self._require_process()
        if process.stdout is None:
            raise RuntimeError("Steam helper stdout is unavailable")
        while True:
            line = process.stdout.readline()
            if not line:
                return_code = process.wait()
                detail = process.stderr.read().strip() if process.stderr else ""
                self._clear_process()
                raise RuntimeError(
                    "Steam web authentication failed "
                    f"(exit code {return_code}): {detail or 'no diagnostic output'}"
                )
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("eventType")
            if event_type == "steam_guard_required":
                self.challenge = SteamGuardChallenge(
                    method=str(event["method"]),
                    email=event.get("email"),
                    previous_code_was_incorrect=bool(event.get("previousCodeWasIncorrect", False)),
                )
                return self.challenge
            if event_type == "auth_state":
                state = SteamAuthState(
                    username=str(event["username"]),
                    refresh_token=str(event["refreshToken"]),
                    guard_data=event.get("guardData"),
                )
                process.wait(timeout=10)
                self._clear_process()
                return state

    def _require_process(self) -> subprocess.Popen[str]:
        if self.process is None:
            raise RuntimeError("Steam web authentication is not running")
        return self.process

    def _clear_process(self) -> None:
        self.process = None
        self.challenge = None

    def close(self) -> None:
        process, self.process = self.process, None
        self.challenge = None
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.write('{"cancel":true}\n')
                process.stdin.flush()
            process.wait(timeout=5)
        except Exception:
            process.kill()
            process.wait()

    def __enter__(self) -> "SteamWebAuthFlow":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
