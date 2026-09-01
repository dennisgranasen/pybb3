from __future__ import annotations

import base64
import json
import socket
import xml.etree.ElementTree as ET
from collections import deque
from typing import Callable, Iterable

from .constants import DEFAULT_CLIENT_VERSION
from .discovery import discover_bb3_endpoint
from .encoding import b64_decode_text, b64_encode_text
from .models import (
    CharacteristicRoll,
    Competition,
    CompetitionSchedule,
    CompetitionSetting,
    Formation,
    GameList,
    GameResult,
    MatchStatistics,
    PlayerImprovements,
    RandomSkillResult,
    TeamRoster,
)
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
        self._inbox: deque[BB3Frame] = deque()
        self._subscribers: dict[str | None, list[Callable[[BB3Frame], None]]] = {}
        self._callback_errors: deque[tuple[BB3Frame, Exception]] = deque()

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
        socket_error: OSError | None = None
        try:
            sock, self.sock = self.sock, None
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError as exc:
                    socket_error = exc
        finally:
            if self._steam_auth is not None:
                self._steam_ticket = None
                self._steam_auth.close()
        if socket_error is not None:
            raise socket_error

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

    def _wait_for(self, expected_name: str, expected_message_token: int) -> BB3Frame:
        queued = self._take_queued(expected_name, expected_message_token)
        if queued is not None:
            return queued
        sock = self._socket()
        while True:
            frame = recv_frame(sock)
            if frame.message_name == expected_name and frame.message_token == expected_message_token:
                return frame
            self._dispatch(frame)

    def _take_queued(
        self, expected_name: str, expected_message_token: int
    ) -> BB3Frame | None:
        for index, frame in enumerate(self._inbox):
            if frame.message_name == expected_name and frame.message_token == expected_message_token:
                self._inbox.rotate(-index)
                result = self._inbox.popleft()
                self._inbox.rotate(index)
                return result
        return None

    def _dispatch(self, frame: BB3Frame) -> None:
        self._inbox.append(frame)
        callbacks = (
            *self._subscribers.get(frame.message_name, ()),
            *self._subscribers.get(None, ()),
        )
        for callback in callbacks:
            try:
                callback(frame)
            except Exception as exc:
                self._callback_errors.append((frame, exc))

    def subscribe(self, message_name: str | None, callback: Callable[[BB3Frame], None]) -> None:
        callbacks = self._subscribers.setdefault(message_name, [])
        if callback not in callbacks:
            callbacks.append(callback)

    def unsubscribe(self, message_name: str | None, callback: Callable[[BB3Frame], None]) -> None:
        callbacks = self._subscribers.get(message_name)
        if callbacks is None:
            return
        try:
            callbacks.remove(callback)
        except ValueError:
            return
        if not callbacks:
            del self._subscribers[message_name]

    def pop_notification(self, message_name: str | None = None) -> BB3Frame | None:
        for index, frame in enumerate(self._inbox):
            if message_name is None or frame.message_name == message_name:
                self._inbox.rotate(-index)
                result = self._inbox.popleft()
                self._inbox.rotate(index)
                return result
        return None

    @property
    def pending_notifications(self) -> tuple[BB3Frame, ...]:
        return tuple(self._inbox)

    def pop_callback_error(self) -> tuple[BB3Frame, Exception] | None:
        return self._callback_errors.popleft() if self._callback_errors else None

    @staticmethod
    def _assert_success(frame: BB3Frame) -> ET.Element:
        root = parse_xml(frame.body)
        result = root.findtext("Result")
        exception = root.find("Exception")
        exceptions = root.find("Exceptions")
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
                f"{frame.message_name} failed (code {code}): "
                f"{redact_text(description) if description else 'Unknown error'}",
                code=code,
                description=description,
                message_name=frame.message_name,
                raw_response=frame.body,
                frame=frame,
            )

        if result is not None and result == "0":
            raise BB3RequestError(
                f"{frame.message_name} Result={result}: {redact_text(frame.body[:4000])}",
                description="Result=0",
                message_name=frame.message_name,
                raw_response=frame.body,
                frame=frame,
            )
        return root

    def keepalive(self) -> None:
        mt = self._next_message_token()
        send_frame(self._socket(), "NotificationKeepAlive", mt, "<NotificationKeepAlive/>")
        self._wait_for("NotificationKeepAlive", mt)

    def request_frame(
        self, request_name: str, response_name: str, extra_xml: str = ""
    ) -> BB3Frame:
        mt = self._next_message_token()
        token = self._next_body_token()
        body = (
            f"<{request_name}><Token>{token}</Token>"
            "<ShouldCache>false</ShouldCache>"
            f"{extra_xml}</{request_name}>"
        )
        send_frame(self._socket(), request_name, mt, body)
        return self._wait_for(response_name, mt)

    def request(
        self, request_name: str, response_name: str, extra_xml: str = ""
    ) -> ET.Element:
        return self._assert_success(
            self.request_frame(request_name, response_name, extra_xml)
        )

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

    def login(self, steam_id: str | None = None, auth_token: str | None = None) -> ET.Element:
        if steam_id is None or auth_token is None:
            if self._steam_ticket is None:
                raise ValueError("Steam credentials are required; use BB3Client.from_steam()")
            steam_id = self._steam_ticket.steam_id
            auth_token = self._steam_ticket.auth_token
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


    # ---------- Games / match results ----------

    @staticmethod
    def _xml_scalar_items(container: str, item: str, values: Iterable[object]) -> str:
        contents = "".join(f"<{item}>{value}</{item}>" for value in values)
        return f"<{container}>{contents}</{container}>"

    @staticmethod
    def _xml_bool_items(container: str, item: str, values: Iterable[bool]) -> str:
        contents = "".join(
            f"<{item}>{str(value).lower()}</{item}>" for value in values
        )
        return f"<{container}>{contents}</{container}>"

    @staticmethod
    def _xml_b64_items(container: str, item: str, values: Iterable[str]) -> str:
        contents = "".join(
            f"<{item}>{b64_encode_text(value)}</{item}>" for value in values
        )
        return f"<{container}>{contents}</{container}>"

    def get_competition_formats(self) -> ET.Element:
        return self.request(
            "RequestGetCompetitionFormats",
            "ResponseGetCompetitionFormats",
        )

    def get_all_races(self) -> ET.Element:
        return self.request(
            "RequestGetAllRaces",
            "ResponseGetAllRaces",
        )

    def get_available_get_games_team_values(self) -> ET.Element:
        return self.request(
            "RequestGetAvailableGetGamesTeamValues",
            "ResponseGetAvailableGetGamesTeamValues",
        )

    def get_games(
        self,
        *,
        size: int = 9,
        start: int = 0,
        is_live: Iterable[bool] = (),
        is_over: Iterable[bool] = (),
        has_replay: Iterable[bool] = (),
        league_ids: Iterable[str] = (),
        competition_ids: Iterable[str] = (),
        gamer_ids: Iterable[str] = (),
        team_ids: Iterable[str] = (),
        max_days_since_game: int = 20000,
        min_rating: int = 0,
        max_rating: int = 0,
        min_team_value: int = 0,
        max_team_value: int = 0,
        game_types: Iterable[int] = (),
        races: Iterable[int] = (),
        own_races: Iterable[int] = (),
        opponent_races: Iterable[int] = (),
        contains_ai: Iterable[bool] = (),
        outcomes: Iterable[int] = (),
        order: int = 0,
        descending: bool = True,
    ) -> ET.Element:
        """Query backend games using the capture-verified filter envelope.

        Enum meanings for ``game_types``, ``outcomes`` and ``order`` are
        intentionally not assigned here. Name filters were only observed empty,
        so this method does not invent encoding semantics for them.
        """
        return self.request(
            "RequestGetGames",
            "ResponseGetGames",
            (
                f"<Size>{size}</Size><Start>{start}</Start>"
                f"{self._xml_bool_items('IsLive', 'IsLiveItem', is_live)}"
                f"{self._xml_bool_items('IsOver', 'IsOverItem', is_over)}"
                f"{self._xml_bool_items('HasReplay', 'HasReplayItem', has_replay)}"
                f"{self._xml_b64_items('LeagueIds', 'LeagueIdsItem', league_ids)}"
                "<LeagueName/>"
                f"{self._xml_b64_items('CompetitionIds', 'CompetitionIdsItem', competition_ids)}"
                "<CompetitionName/>"
                f"{self._xml_b64_items('GamerIds', 'GamerIdsItem', gamer_ids)}"
                "<GamerName/>"
                f"{self._xml_b64_items('TeamIds', 'TeamIdsItem', team_ids)}"
                "<TeamName/>"
                f"<MaxDaysSinceGame>{max_days_since_game}</MaxDaysSinceGame>"
                f"<MinRating>{min_rating}</MinRating><MaxRating>{max_rating}</MaxRating>"
                f"<MinTeamValue>{min_team_value}</MinTeamValue>"
                f"<MaxTeamValue>{max_team_value}</MaxTeamValue>"
                f"{self._xml_scalar_items('GameType', 'GameTypeItem', game_types)}"
                f"{self._xml_scalar_items('Races', 'RacesItem', races)}"
                f"{self._xml_scalar_items('OwnRaces', 'OwnRacesItem', own_races)}"
                f"{self._xml_scalar_items('OpponentRaces', 'OpponentRacesItem', opponent_races)}"
                f"{self._xml_bool_items('ContainsAi', 'ContainsAiItem', contains_ai)}"
                f"{self._xml_scalar_items('Outcome', 'OutcomeItem', outcomes)}"
                f"<Order>{order}</Order>"
                f"<Descending>{str(descending).lower()}</Descending>"
            ),
        )

    def get_games_model(self, **kwargs) -> GameList:
        return GameList.from_response(self.get_games(**kwargs))

    def get_game_result(self, game_id: str) -> ET.Element:
        return self.request(
            "RequestGetGameResult",
            "ResponseGetGameResult",
            f"<GameId>{b64_encode_text(game_id)}</GameId>",
        )

    def get_game_result_model(self, game_id: str) -> GameResult:
        return GameResult.from_response(self.get_game_result(game_id))

    def get_match_statistics(self, match_id: str) -> ET.Element:
        return self.request(
            "RequestGetMatchStatistics",
            "ResponseGetMatchStatistics",
            f"<MatchId>{b64_encode_text(match_id)}</MatchId>",
        )

    def get_match_statistics_model(self, match_id: str) -> MatchStatistics:
        return MatchStatistics.from_response(self.get_match_statistics(match_id))

    def get_spp_result(self, game_id: str) -> ET.Element:
        return self.request(
            "RequestGetSppResult",
            "ResponseGetSppResult",
            f"<GameId>{b64_encode_text(game_id)}</GameId>",
        )

    def get_match_dice_rolls(self, match_id: str) -> ET.Element:
        return self.request(
            "RequestGetMatchDiceRolls",
            "ResponseGetMatchDiceRolls",
            f"<MatchId>{b64_encode_text(match_id)}</MatchId>",
        )

    def get_battle_pass_game_xp_gain(self, game_id: str) -> ET.Element:
        return self.request(
            "RequestGetBattlePassGameXpGain",
            "ResponseGetBattlePassGameXpGain",
            f"<GameId>{b64_encode_text(game_id)}</GameId>",
        )

    # ---------- Competitions ----------

    def get_competition(self, competition_id: str) -> ET.Element:
        return self.request(
            "RequestGetCompetition",
            "ResponseGetCompetition",
            f"<IdCompetition>{b64_encode_text(competition_id)}</IdCompetition>",
        )

    def get_competition_model(self, competition_id: str) -> Competition:
        return Competition.from_response(self.get_competition(competition_id))

    def get_competition_menu(self, competition_id: str) -> ET.Element:
        return self.request(
            "RequestGetCompetitionMenu",
            "ResponseGetCompetitionMenu",
            f"<CompetitionId>{b64_encode_text(competition_id)}</CompetitionId>",
        )

    def get_competition_setting(self, setting_id: str) -> ET.Element:
        return self.request(
            "RequestGetCompetitionSetting",
            "ResponseGetCompetitionSetting",
            f"<SettingId>{b64_encode_text(setting_id)}</SettingId>",
        )

    def get_competition_setting_model(self, setting_id: str) -> CompetitionSetting:
        return CompetitionSetting.from_response(self.get_competition_setting(setting_id))

    def get_competition_gamer_ban_duration(
        self, competition_id: str, gamer_id: str
    ) -> ET.Element:
        return self.request(
            "RequestGetCompetitionGamerBanDuration",
            "ResponseGetCompetitionGamerBanDuration",
            f"<CompetitionId>{b64_encode_text(competition_id)}</CompetitionId>"
            f"<GamerId>{b64_encode_text(gamer_id)}</GamerId>",
        )

    def get_competition_participants_by_gamer(
        self, competition_id: str, gamer_id: str
    ) -> ET.Element:
        # Capture-observed response name is ResponseGetCompetitionRanking.
        return self.request(
            "RequestGetCompetitionParticipantsByGamer",
            "ResponseGetCompetitionRanking",
            f"<CompetitionId>{b64_encode_text(competition_id)}</CompetitionId>"
            f"<GamerId>{b64_encode_text(gamer_id)}</GamerId>",
        )

    def get_next_match(self, participant_id: str) -> ET.Element:
        return self.request(
            "RequestGetNextMatch",
            "ResponseGetNextMatch",
            f"<ParticipantId>{b64_encode_text(participant_id)}</ParticipantId>",
        )

    def get_competition_ranking(
        self,
        competition_id: str,
        *,
        size: int = 18,
        start: int = 0,
        races: Iterable[int] = (),
    ) -> ET.Element:
        return self.request(
            "RequestGetCompetitionRanking",
            "ResponseGetCompetitionRanking",
            (
                f"<Size>{size}</Size><Start>{start}</Start>"
                f"<IdCompetition>{b64_encode_text(competition_id)}</IdCompetition>"
                f"{self._xml_scalar_items('Races', 'RacesItem', races)}"
            ),
        )

    def get_competition_gamer_registered_teams(
        self, competition_id: str, gamer_id: str | None = None
    ) -> ET.Element:
        gamer_xml = (
            f"<GamerId>{b64_encode_text(gamer_id)}</GamerId>"
            if gamer_id
            else "<GamerId/>"
        )
        return self.request(
            "RequestGetCompetitionGamerRegisteredTeams",
            "ResponseGetCompetitionGamerRegisteredTeams",
            gamer_xml
            + f"<CompetitionId>{b64_encode_text(competition_id)}</CompetitionId>",
        )

    def get_competition_day(self, competition_id: str) -> int:
        root = self.request(
            "RequestGetCompetitionDay",
            "ResponseGetCompetitionDay",
            f"<IdCompetition>{b64_encode_text(competition_id)}</IdCompetition>",
        )
        value = root.findtext("Value")
        if value is None:
            raise BB3RequestError("ResponseGetCompetitionDay contained no Value")
        return int(value)

    def get_competition_schedule(self, competition_id: str, day: int) -> ET.Element:
        return self.request(
            "RequestGetCompetitionSchedule",
            "ResponseGetCompetitionSchedule",
            f"<IdCompetition>{b64_encode_text(competition_id)}</IdCompetition>"
            f"<Day>{day}</Day>",
        )

    def get_competition_schedule_model(
        self, competition_id: str, day: int
    ) -> CompetitionSchedule:
        return CompetitionSchedule.from_response(
            self.get_competition_schedule(competition_id, day)
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

    def get_teams_of_gamer(
        self,
        *,
        size: int = 9,
        start: int = 0,
        order: int = 4,
        descending: bool = True,
        include_templates: bool = False,
    ) -> ET.Element:
        return self.request(
            "RequestGetTeamsOfGamer",
            "ResponseGetTeams",
            (
                f"<Size>{size}</Size><Start>{start}</Start><GamerId/><Races/>"
                f"<Order>{order}</Order>"
                f"<Descending>{str(descending).lower()}</Descending>"
                "<Name/><Competing/><IsCustom/>"
                "<IsTemplate>"
                f"<IsTemplateItem>{str(include_templates).lower()}</IsTemplateItem>"
                "</IsTemplate>"
            ),
        )

    def get_teams_competitions(self, team_ids: Iterable[str]) -> ET.Element:
        items = "".join(
            f"<TeamIdsItem>{b64_encode_text(team_id)}</TeamIdsItem>"
            for team_id in team_ids
        )
        return self.request(
            "RequestGetTeamsCompetitions",
            "ResponseGetTeamsCompetitions",
            f"<TeamIds>{items}</TeamIds>",
        )

    def get_team_roster(self, team_id: str) -> ET.Element:
        # Captured wire field is IdTeam (not TeamId).
        return self.request(
            "RequestGetTeamRoster",
            "ResponseGetTeamRoster",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>",
        )

    def get_team_roster_model(self, team_id: str) -> TeamRoster:
        return TeamRoster.from_response(self.get_team_roster(team_id))

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
        motto_xml = f"<Motto>{b64_encode_text(motto)}</Motto>" if motto else "<Motto/>"
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
                f"<Name>{b64_encode_text(name)}</Name><Race>{race_id}</Race>"
                f"{motto_xml}<IsCustom>{str(is_custom).lower()}</IsCustom>"
                f"{recruitment_xml}{special_rule_xml}"
            ),
        )
        encoded = root.findtext("IdTeam")
        if not encoded:
            raw = ET.tostring(root, encoding="unicode")
            raise BB3RequestError(
                "ResponseCreateTeam did not contain IdTeam: "
                f"{redact_text(raw[:4000])}",
                message_name="ResponseCreateTeam",
                raw_response=raw,
            )
        return b64_decode_text(encoded)

    def delete_team(self, team_id: str) -> ET.Element:
        return self.request(
            "RequestDeleteTeam",
            "ResponseDeleteTeam",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>",
        )

    def set_team_name(self, team_id: str, name: str) -> ET.Element:
        return self.request(
            "RequestSetTeamName",
            "ResponseSetTeamName",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
            f"<Name>{b64_encode_text(name)}</Name>",
        )

    def set_team_motto(self, team_id: str, motto: str) -> ET.Element:
        return self.request(
            "RequestSetTeamMotto",
            "ResponseSetTeamMotto",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
            f"<Motto>{b64_encode_text(motto)}</Motto>",
        )

    # ---------- Players ----------

    def hire_player_from_position(self, team_id: str, position_id: int) -> str:
        root = self.request(
            "RequestHirePlayerFromPosition",
            "ResponseHirePlayerFromPosition",
            f"<TeamId>{b64_encode_text(team_id)}</TeamId><Position>{position_id}</Position>",
        )
        encoded = root.findtext("IdPlayer")
        if not encoded:
            raise BB3RequestError("HirePlayerFromPosition returned no IdPlayer")
        return b64_decode_text(encoded)

    def set_player_name(self, player_id: str, name: str) -> ET.Element:
        return self.request(
            "RequestSetPlayerName",
            "ResponseSetPlayerName",
            f"<IdPlayer>{b64_encode_text(player_id)}</IdPlayer>"
            f"<Name>{b64_encode_text(name)}</Name>",
        )

    def fire_players(
        self, team_id: str, players: Iterable[tuple[str, bool]]
    ) -> ET.Element:
        items = "".join(
            "<PlayerFireInfosItem>"
            f"<PlayerId>{b64_encode_text(player_id)}</PlayerId>"
            f"<TemporarilyRetire>{str(temp).lower()}</TemporarilyRetire>"
            "</PlayerFireInfosItem>"
            for player_id, temp in players
        )
        return self.request(
            "RequestFirePlayers",
            "ResponseFirePlayers",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
            "<IdPlayers/>"
            f"<PlayerFireInfos>{items}</PlayerFireInfos>",
        )

    # ---------- Player advancement ----------

    def get_player_improvements(self, player_id: str) -> PlayerImprovements:
        root = self.request(
            "RequestGetPlayerImprovements",
            "ResponseGetPlayerImprovements",
            f"<IdPlayer>{b64_encode_text(player_id)}</IdPlayer>",
        )
        return PlayerImprovements.from_response(root)

    def add_player_random_skill(self, player_id: str, category: int) -> RandomSkillResult:
        root = self.request(
            "RequestAddPlayerRandomSkill",
            "ResponseAddPlayerRandomSkill",
            f"<IdPlayer>{b64_encode_text(player_id)}</IdPlayer><Category>{category}</Category>",
        )
        skill_text = root.findtext("Skill")
        if skill_text is None:
            raise BB3RequestError("ResponseAddPlayerRandomSkill contained no Skill")
        return RandomSkillResult(
            skill_id=int(skill_text),
            has_left=(root.findtext("HasLeft") or "0").lower() in {"1", "true"},
        )

    def add_player_skill(self, player_id: str, skill_id: int) -> ET.Element:
        # The same endpoint is used for chosen primary and chosen secondary skills.
        return self.request(
            "RequestAddPlayerSkill",
            "ResponseAddPlayerSkill",
            f"<IdPlayer>{b64_encode_text(player_id)}</IdPlayer><Skill>{skill_id}</Skill>",
        )

    def begin_increase_player_characteristic(self, player_id: str) -> CharacteristicRoll:
        root = self.request(
            "RequestBeginIncreasePlayerCharacteristic",
            "ResponseBeginIncreasePlayerCharacteristic",
            f"<PlayerId>{b64_encode_text(player_id)}</PlayerId>",
        )
        return CharacteristicRoll.from_response(root)

    def choose_increase_player_characteristic(
        self, player_id: str, characteristic_id: int
    ) -> ET.Element:
        return self.request(
            "RequestChooseIncreasePlayerCharacteristic",
            "ResponseChooseIncreasePlayerCharacteristic",
            f"<PlayerId>{b64_encode_text(player_id)}</PlayerId>"
            f"<ChosenCharacteristic>{characteristic_id}</ChosenCharacteristic>",
        )

    # ---------- Team improvements ----------

    def update_team_improvements(
        self, team_id: str, changes: Iterable[tuple[int, int]]
    ) -> ET.Element:
        items = "".join(
            "<ImprovementsItem>"
            f"<ImprovementId>{improvement_id}</ImprovementId>"
            f"<Quantity>{quantity_delta}</Quantity>"
            "</ImprovementsItem>"
            for improvement_id, quantity_delta in changes
        )
        return self.request(
            "RequestUpdateTeamImprovements",
            "ResponseUpdateTeamImprovements",
            f"<TeamId>{b64_encode_text(team_id)}</TeamId>"
            f"<Improvements>{items}</Improvements>",
        )

    # ---------- Collection / cosmetics ----------

    def collection_items(self, tag: str, *, size: int = 100, start: int = 0) -> ET.Element:
        return self.request(
            "RequestCollectionItems",
            "ResponseCollectionItems",
            f"<Size>{size}</Size><Start>{start}</Start>"
            f"<Tags><TagsItem>{b64_encode_text(tag)}</TagsItem></Tags>"
            "<Search/><Filter/><Sort/><Order/><Rarities/><ExcludedTags/>",
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
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
            f"<IdJerseyPattern>{b64_encode_text(item_id)}</IdJerseyPattern>",
        )

    def get_team_colors(self, team_id: str) -> ET.Element:
        return self.request(
            "RequestGetTeamColors",
            "ResponseGetTeamColors",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>",
        )

    def _set_cosmetic(self, team_id: str, slot: str, item_id: str) -> ET.Element:
        return self.request(
            f"RequestSetTeam{slot}",
            f"ResponseSetTeam{slot}",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
            f"<Id{slot}>{b64_encode_text(item_id)}</Id{slot}>",
        )

    def _set_color(self, team_id: str, slot: str, color_id: str) -> ET.Element:
        return self.request(
            f"RequestSetTeam{slot}Color",
            f"ResponseSetTeam{slot}Color",
            f"<IdTeam>{b64_encode_text(team_id)}</IdTeam>"
            f"<IdColor>{b64_encode_text(color_id)}</IdColor>",
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
            formation.data_dict(), indent=1, separators=(",", ": ")
        ).replace("\n", "\r\n")
        root = self.request(
            "RequestSaveFormation",
            "ResponseSaveFormation",
            "<Formation>"
            f"{formation_id_xml}"
            f"<TeamId>{b64_encode_text(formation.team_id)}</TeamId>"
            f"<Name>{b64_encode_text(formation.name)}</Name>"
            f"<Data>{b64_encode_text(data_text)}</Data>"
            f"<Type>{formation.formation_type}</Type>"
            "</Formation>",
        )
        encoded = root.findtext("Formation/Id")
        if not encoded:
            raise BB3RequestError("SaveFormation returned no Formation/Id")
        return b64_decode_text(encoded)

    def remove_formations(
        self, team_id: str, formation_ids: Iterable[str]
    ) -> ET.Element:
        items = "".join(
            f"<FormationIdsItem>{b64_encode_text(fid)}</FormationIdsItem>"
            for fid in formation_ids
        )
        return self.request(
            "RequestRemoveFormations",
            "ResponseRemoveFormations",
            f"<FormationIds>{items}</FormationIds>"
            f"<TeamId>{b64_encode_text(team_id)}</TeamId>",
        )
