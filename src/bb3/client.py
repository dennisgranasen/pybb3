from __future__ import annotations

import base64
import json
import socket
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from .constants import DEFAULT_CLIENT_VERSION
from .discovery import discover_bb3_endpoint
from .encoding import b64_decode_text, b64_encode_text
from .models import Formation
from .protocol import BB3Frame, BB3ProtocolError, parse_xml, recv_frame, send_frame
from .replay import decode_replay_data
from .security import redact_text


class BB3RequestError(BB3ProtocolError):
    """A syntactically valid BB3 response that reports request failure."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        description: str | None = None,
        message_name: str | None = None,
        raw_response: str | None = None,
        frame: BB3Frame | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.description = description
        self.message_name = message_name
        self.raw_response = raw_response
        self.frame = frame


class BB3Client:
    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        client_version: str = DEFAULT_CLIENT_VERSION,
        timeout: float = 30.0,
        steam_auth=None,
    ):
        self.host = host
        self.port = port
        self.client_version = client_version
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.message_token = 0
        self.body_token = 0
        self._steam_auth = steam_auth
        self._steam_ticket = None

    @classmethod
    def from_steam(cls, *, helper=None, cache_path=".bb3-steam-auth.json", **kwargs):
        from .steam import SteamAuthProcess

        return cls(steam_auth=SteamAuthProcess(helper, cache_path=cache_path), **kwargs)

    def connect(self) -> None:
        if self.sock is not None:
            return
        host = self.host
        port = self.port
        if host is None or port is None:
            endpoint = discover_bb3_endpoint(self.client_version)
            host, port = endpoint.host, endpoint.port
            self.host, self.port = host, port
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(self.timeout)

    def close(self) -> None:
        try:
            if self.sock is not None:
                self.sock.close()
                self.sock = None
        finally:
            if self._steam_auth is not None:
                self._steam_auth.close()
                self._steam_ticket = None

    def __enter__(self) -> "BB3Client":
        try:
            if self._steam_auth is not None:
                self._steam_ticket = self._steam_auth.start()
            self.connect()
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _next_message_token(self) -> int:
        self.message_token += 1
        return self.message_token

    def _next_body_token(self) -> int:
        self.body_token += 1
        return self.body_token

    def _socket(self) -> socket.socket:
        if self.sock is None:
            raise RuntimeError("BB3Client is not connected")
        return self.sock

    def _wait_for(
        self,
        expected_name: str,
        expected_message_token: int,
    ) -> BB3Frame:
        sock = self._socket()
        while True:
            frame = recv_frame(sock)
            if frame.message_name == "KeepAliveAdvice":
                continue
            if (
                frame.message_name == expected_name
                and frame.message_token == expected_message_token
            ):
                return frame
            # Notifications and unrelated asynchronous responses are ignored here.
            # A production event dispatcher can be layered on later.

    @staticmethod
    def _assert_success(frame: BB3Frame) -> ET.Element:
        root = parse_xml(frame.body)

        result = root.findtext("Result")

        exception = root.find("Exception")
        exceptions = root.find("Exceptions")

        # Some responses wrap one or more exception records in <Exceptions>.
        if exception is None and exceptions is not None and len(exceptions):
            exception = exceptions.find("Exception")
            if exception is None:
                exception = exceptions[0]

        if exception is not None:
            code_text = exception.findtext("Code")
            desc_b64 = exception.findtext("Desc")

            try:
                code = int(code_text) if code_text else None
            except ValueError:
                code = None
            description = None

            if desc_b64:
                try:
                    description = base64.b64decode(desc_b64).decode("utf-8")
                except (ValueError, UnicodeDecodeError, base64.binascii.Error):
                    description = desc_b64

            raise BB3RequestError(
                f"{frame.message_name} failed "
                f"(code {code}): "
                f"{redact_text(description) if description else 'Unknown error'}",
                code=code,
                description=description,
                message_name=frame.message_name,
                raw_response=frame.body,
                frame=frame,
            )

        # Explicit Result field: 0 = failure, non-zero = success
        if result is not None:
            if result == "0":
                raise BB3RequestError(
                    f"{frame.message_name} Result={result}: "
                    f"{redact_text(frame.body[:4000])}",
                    description="Result=0",
                    message_name=frame.message_name,
                    raw_response=frame.body,
                    frame=frame,
                )

            return root

        # No Result and no exception = valid success response
        return root

    def keepalive(self) -> None:
        mt = self._next_message_token()
        send_frame(
            self._socket(),
            "NotificationKeepAlive",
            mt,
            "<NotificationKeepAlive/>",
        )
        self._wait_for("NotificationKeepAlive", mt)

    def request_frame(
        self,
        request_name: str,
        response_name: str,
        extra_xml: str = "",
    ) -> BB3Frame:
        """Send a request and return its raw correlated response frame."""
        mt = self._next_message_token()
        token = self._next_body_token()
        body = (
            f"<{request_name}>"
            f"<Token>{token}</Token>"
            "<ShouldCache>false</ShouldCache>"
            f"{extra_xml}"
            f"</{request_name}>"
        )
        send_frame(self._socket(), request_name, mt, body)
        return self._wait_for(response_name, mt)

    def request(
        self,
        request_name: str,
        response_name: str,
        extra_xml: str = "",
    ) -> ET.Element:
        """Send a request and return its validated XML response root."""
        frame = self.request_frame(request_name, response_name, extra_xml)
        return self._assert_success(frame)

    def get_server_status(self) -> ET.Element:
        return self.request(
            "RequestGetServerStatus",
            "ResponseGetServerStatus",
            f"<Lang>{b64_encode_text('en')}</Lang>",
        )

    def get_gamer_config(self, steam_id: str) -> ET.Element:
        return self.request(
            "RequestGetGamerConfig",
            "ResponseGetGamerConfig",
            (
                f"<BootstrapKey>{b64_encode_text(self.client_version)}</BootstrapKey>"
                f"<PlatformName>{b64_encode_text('Windows')}</PlatformName>"
                f"<OssName>{b64_encode_text('Steam')}</OssName>"
                f"<UserId>{b64_encode_text(steam_id)}</UserId>"
            ),
        )

    def login(
        self,
        steam_id: str | None = None,
        auth_token: str | None = None,
    ) -> ET.Element:
        if steam_id is None or auth_token is None:
            if self._steam_ticket is None:
                raise ValueError(
                    "Steam credentials are required; use BB3Client.from_steam()"
                )
            steam_id = self._steam_ticket.steam_id
            auth_token = self._steam_ticket.auth_token
        # Observed BB3 startup performs keepalive, status/config, then login.
        self.keepalive()
        self.get_server_status()
        self.get_gamer_config(steam_id)

        return self.request(
            "RequestLogin",
            "ResponseLogin",
            (
                f"<AuthService>{b64_encode_text('steam')}</AuthService>"
                f"<AuthToken>{auth_token}</AuthToken>"
                f"<Platform>{b64_encode_text('steam')}</Platform>"
                "<PlatformToken/>"
                f"<ClientVersion>{b64_encode_text(self.client_version)}</ClientVersion>"
                f"<Lang>{b64_encode_text('en')}</Lang>"
                "<IsCrossPlayEnabled>true</IsCrossPlayEnabled>"
            ),
        )

    # ---------- Replay ----------

    def download_replay(self, game_id: str) -> bytes:
        root = self.request(
            "RequestDownloadReplay",
            "ResponseDownloadReplay",
            f"<GameId>{b64_encode_text(game_id)}</GameId>",
        )
        replay_data = root.findtext("ReplayData")
        if not replay_data:
            raise BB3RequestError("Replay response contained no ReplayData")
        return decode_replay_data(replay_data)

    # ---------- Teams ----------

    def get_team(self, team_id: str) -> ET.Element:
        return self.request(
            "RequestGetTeam",
            "ResponseGetTeam",
            f"<TeamId>{b64_encode_text(team_id)}</TeamId>",
        )

    def get_team_roster(self, team_id: str) -> ET.Element:
        return self.request(
            "RequestGetTeamRoster",
            "ResponseGetTeamRoster",
            f"<TeamId>{b64_encode_text(team_id)}</TeamId>",
        )

    def create_team(
        self,
        name: str,
        race_id: int,
        *,
        motto: str | None = None,
        is_custom: bool = False,
        team_recruitment_id: str | None = None,
        chosen_special_rule: int | None = None,
    ) -> str:
        motto_xml = (
            f"<Motto>{b64_encode_text(motto)}</Motto>" if motto else "<Motto/>"
        )
        recruitment_xml = (
            f"<TeamRecruitmentId>{b64_encode_text(team_recruitment_id)}</TeamRecruitmentId>"
            if team_recruitment_id
            else "<TeamRecruitmentId/>"
        )
        special_rule_xml = (
            f"<ChosenSpecialRule>{chosen_special_rule}</ChosenSpecialRule>"
            if chosen_special_rule is not None
            else "<ChosenSpecialRule/>"
        )

        root = self.request(
            "RequestCreateTeam",
            "ResponseCreateTeam",
            (
                f"<Name>{b64_encode_text(name)}</Name>"
                f"<Race>{race_id}</Race>"
                f"{motto_xml}"
                f"<IsCustom>{str(is_custom).lower()}</IsCustom>"
                f"{recruitment_xml}"
                f"{special_rule_xml}"
            ),
        )

        encoded = root.findtext("IdTeam")
        if not encoded:
            raise BB3RequestError(
                "ResponseCreateTeam did not contain IdTeam: "
                f"{redact_text(ET.tostring(root, encoding='unicode')[:4000])}",
                message_name="ResponseCreateTeam",
                raw_response=ET.tostring(root, encoding="unicode"),
            )

        return b64_decode_text(encoded)

    def delete_team(self, team_id: str) -> ET.Element:
        # RequestDeleteTeam was observed but its body was not captured in the
        # material used to build this repo. Keep this intentionally explicit.
        raise NotImplementedError(
            "RequestDeleteTeam endpoint is verified, but its exact body "
            "was not included in the captured corpus used here."
        )

    def set_team_name(self, team_id: str, name: str) -> ET.Element:
        return self.request(
            "RequestSetTeamName",
            "ResponseSetTeamName",
            (
                f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
                f"<Name>{b64_encode_text(name)}</Name>"
            ),
        )

    def set_team_motto(self, team_id: str, motto: str) -> ET.Element:
        return self.request(
            "RequestSetTeamMotto",
            "ResponseSetTeamMotto",
            (
                f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
                f"<Motto>{b64_encode_text(motto)}</Motto>"
            ),
        )

    # ---------- Players ----------

    def hire_player_from_position(self, team_id: str, position_id: int) -> str:
        root = self.request(
            "RequestHirePlayerFromPosition",
            "ResponseHirePlayerFromPosition",
            (
                f"<TeamId>{b64_encode_text(team_id)}</TeamId>"
                f"<Position>{position_id}</Position>"
            ),
        )
        encoded = root.findtext("IdPlayer")
        if not encoded:
            raise BB3RequestError("HirePlayerFromPosition returned no IdPlayer")
        return b64_decode_text(encoded)

    def set_player_name(self, player_id: str, name: str) -> ET.Element:
        return self.request(
            "RequestSetPlayerName",
            "ResponseSetPlayerName",
            (
                f"<IdPlayer>{b64_encode_text(player_id)}</IdPlayer>"
                f"<Name>{b64_encode_text(name)}</Name>"
            ),
        )

    def fire_players(
        self,
        team_id: str,
        players: Iterable[tuple[str, bool]],
    ) -> ET.Element:
        items = "".join(
            (
                "<PlayerFireInfosItem>"
                f"<PlayerId>{b64_encode_text(player_id)}</PlayerId>"
                f"<TemporarilyRetire>{str(temp).lower()}</TemporarilyRetire>"
                "</PlayerFireInfosItem>"
            )
            for player_id, temp in players
        )
        return self.request(
            "RequestFirePlayers",
            "ResponseFirePlayers",
            (
                f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
                "<IdPlayers/>"
                f"<PlayerFireInfos>{items}</PlayerFireInfos>"
            ),
        )

    # ---------- Improvements ----------

    def update_team_improvements(
        self,
        team_id: str,
        changes: Iterable[tuple[int, int]],
    ) -> ET.Element:
        items = "".join(
            (
                "<ImprovementsItem>"
                f"<ImprovementId>{improvement_id}</ImprovementId>"
                f"<Quantity>{quantity_delta}</Quantity>"
                "</ImprovementsItem>"
            )
            for improvement_id, quantity_delta in changes
        )
        return self.request(
            "RequestUpdateTeamImprovements",
            "ResponseUpdateTeamImprovements",
            (
                f"<TeamId>{b64_encode_text(team_id)}</TeamId>"
                f"<Improvements>{items}</Improvements>"
            ),
        )

    # ---------- Collection / cosmetics ----------

    def collection_items(
        self,
        tag: str,
        *,
        size: int = 100,
        start: int = 0,
    ) -> ET.Element:
        return self.request(
            "RequestCollectionItems",
            "ResponseCollectionItems",
            (
                f"<Size>{size}</Size>"
                f"<Start>{start}</Start>"
                f"<Tags><TagsItem>{b64_encode_text(tag)}</TagsItem></Tags>"
                "<Search/><Filter/><Sort/><Order/><Rarities/><ExcludedTags/>"
            ),
        )

    def get_team_jersey_pattern(self, team_id: str) -> ET.Element:
        return self.request(
            "RequestGetTeamJerseyPattern",
            "ResponseGetTeamJerseyPattern",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>",
        )

    def set_team_jersey_pattern(self, team_id: str, item_id: str) -> ET.Element:
        return self.request(
            "RequestSetTeamJerseyPattern",
            "ResponseSetTeamJerseyPattern",
            (
                f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
                f"<IdJerseyPattern>{b64_encode_text(item_id)}</IdJerseyPattern>"
            ),
        )

    def get_team_colors(self, team_id: str) -> ET.Element:
        return self.request(
            "RequestGetTeamColors",
            "ResponseGetTeamColors",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>",
        )

    def _set_cosmetic(self, team_id: str, slot: str, item_id: str) -> ET.Element:
        request_name = f"RequestSetTeam{slot}"
        response_name = f"ResponseSetTeam{slot}"
        return self.request(
            request_name,
            response_name,
            (
                f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
                f"<Id{slot}>{b64_encode_text(item_id)}</Id{slot}>"
            ),
        )

    def _set_color(self, team_id: str, slot: str, color_id: str) -> ET.Element:
        return self.request(
            f"RequestSetTeam{slot}Color",
            f"ResponseSetTeam{slot}Color",
            (
                f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
                f"<IdColor>{b64_encode_text(color_id)}</IdColor>"
            ),
        )

    def set_team_primary_color(self, team_id: str, color_id: str) -> ET.Element:
        return self._set_color(team_id, "Primary", color_id)

    def set_team_secondary_color(self, team_id: str, color_id: str) -> ET.Element:
        return self._set_color(team_id, "Secondary", color_id)

    def set_team_tertiary_color(self, team_id: str, color_id: str) -> ET.Element:
        return self._set_color(team_id, "Tertiary", color_id)

    def set_team_cheerleader(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "Cheerleader", item_id)

    def set_team_coach(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "Coach", item_id)

    def set_team_pitch(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "Pitch", item_id)

    def set_team_stadium(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "Stadium", item_id)

    def set_team_coach_zone(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "CoachZone", item_id)

    def set_team_staff_zone(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "StaffZone", item_id)

    def set_team_cheerleader_zone(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "CheerleaderZone", item_id)

    def set_team_dice(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "Dice", item_id)

    def set_team_ball(self, team_id: str, item_id: str) -> ET.Element:
        return self._set_cosmetic(team_id, "Ball", item_id)

    # ---------- Formations ----------

    def get_team_formations(self, team_id: str) -> ET.Element:
        return self.request(
            "RequestGetTeamFormations",
            "ResponseGetTeamFormations",
            f"<TeamId>{b64_encode_text(team_id)}</TeamId>",
        )

    def save_formation(self, formation: Formation) -> str:
        formation_id_xml = (
            f"<Id>{b64_encode_text(formation.formation_id)}</Id>"
            if formation.formation_id
            else "<Id/>"
        )

        data_text = json.dumps(
            formation.data_dict(),
            indent=1,
            separators=(",", ": "),
        )
        # Captured client used CRLF-formatted JSON; servers generally parse the
        # content semantically, but emit CRLF to stay close to observed traffic.
        data_text = data_text.replace("\n", "\r\n")

        root = self.request(
            "RequestSaveFormation",
            "ResponseSaveFormation",
            (
                "<Formation>"
                f"{formation_id_xml}"
                f"<TeamId>{b64_encode_text(formation.team_id)}</TeamId>"
                f"<Name>{b64_encode_text(formation.name)}</Name>"
                f"<Data>{b64_encode_text(data_text)}</Data>"
                f"<Type>{formation.formation_type}</Type>"
                "</Formation>"
            ),
        )

        encoded = root.findtext("Formation/Id")
        if not encoded:
            raise BB3RequestError("SaveFormation returned no Formation/Id")
        return b64_decode_text(encoded)

    def remove_formations(
        self,
        team_id: str,
        formation_ids: Iterable[str],
    ) -> ET.Element:
        items = "".join(
            f"<FormationIdsItem>{b64_encode_text(fid)}</FormationIdsItem>"
            for fid in formation_ids
        )
        return self.request(
            "RequestRemoveFormations",
            "ResponseRemoveFormations",
            (
                f"<FormationIds>{items}</FormationIds>"
                f"<TeamId>{b64_encode_text(team_id)}</TeamId>"
            ),
        )
