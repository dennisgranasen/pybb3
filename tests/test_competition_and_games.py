from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

from bb3.client import BB3Client
from bb3.models import (
    CompetitionSchedule,
    CompetitionSetting,
    GameList,
    GameResult,
    MatchStatistics,
)


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def capture_request(client: BB3Client, monkeypatch):
    seen = {}

    def fake(request_name, response_name, extra_xml=""):
        seen["request"] = request_name
        seen["response"] = response_name
        seen["extra"] = extra_xml
        if response_name == "ResponseGetCompetitionDay":
            return ET.fromstring("<ResponseGetCompetitionDay><Value>9</Value></ResponseGetCompetitionDay>")
        return ET.fromstring(f"<{response_name}/>")

    monkeypatch.setattr(client, "request", fake)
    return seen


def test_competition_request_contracts(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    seen = capture_request(client, monkeypatch)

    client.get_competition("competition-uuid")
    assert seen == {
        "request": "RequestGetCompetition",
        "response": "ResponseGetCompetition",
        "extra": f"<IdCompetition>{b64('competition-uuid')}</IdCompetition>",
    }

    client.get_competition_setting("setting-uuid")
    assert seen == {
        "request": "RequestGetCompetitionSetting",
        "response": "ResponseGetCompetitionSetting",
        "extra": f"<SettingId>{b64('setting-uuid')}</SettingId>",
    }

    assert client.get_competition_day("competition-uuid") == 9
    assert seen["request"] == "RequestGetCompetitionDay"
    assert seen["extra"] == f"<IdCompetition>{b64('competition-uuid')}</IdCompetition>"

    client.get_competition_schedule("competition-uuid", 9)
    assert seen["request"] == "RequestGetCompetitionSchedule"
    assert seen["response"] == "ResponseGetCompetitionSchedule"
    assert seen["extra"] == (
        f"<IdCompetition>{b64('competition-uuid')}</IdCompetition><Day>9</Day>"
    )


def test_game_and_match_request_contracts(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    seen = capture_request(client, monkeypatch)

    client.get_game_result("game-uuid")
    assert seen["request"] == "RequestGetGameResult"
    assert seen["response"] == "ResponseGetGameResult"
    assert seen["extra"] == f"<GameId>{b64('game-uuid')}</GameId>"

    client.get_match_statistics("match-uuid")
    assert seen["request"] == "RequestGetMatchStatistics"
    assert seen["response"] == "ResponseGetMatchStatistics"
    assert seen["extra"] == f"<MatchId>{b64('match-uuid')}</MatchId>"

    client.get_spp_result("game-uuid")
    assert seen["request"] == "RequestGetSppResult"
    assert seen["response"] == "ResponseGetSppResult"

    client.get_match_dice_rolls("match-uuid")
    assert seen["request"] == "RequestGetMatchDiceRolls"
    assert seen["response"] == "ResponseGetMatchDiceRolls"


def test_get_games_filter_envelope(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    seen = capture_request(client, monkeypatch)

    client.get_games(
        team_ids=["team-uuid"],
        competition_ids=["competition-uuid"],
        is_live=[True, False],
        has_replay=[True, False],
        game_types=[0, 1, 2, 4],
        outcomes=[0, 1, 2],
    )

    extra = seen["extra"]
    assert seen["request"] == "RequestGetGames"
    assert seen["response"] == "ResponseGetGames"
    assert f"<TeamIdsItem>{b64('team-uuid')}</TeamIdsItem>" in extra
    assert f"<CompetitionIdsItem>{b64('competition-uuid')}</CompetitionIdsItem>" in extra
    assert "<IsLiveItem>true</IsLiveItem><IsLiveItem>false</IsLiveItem>" in extra
    assert "<HasReplayItem>true</HasReplayItem><HasReplayItem>false</HasReplayItem>" in extra
    assert "<GameTypeItem>4</GameTypeItem>" in extra
    assert "<OutcomeItem>2</OutcomeItem>" in extra


def test_competition_setting_model():
    root = ET.fromstring(
        """<ResponseGetCompetitionSetting><Setting>
        <RedraftOnTeamRegistration>0</RedraftOnTeamRegistration>
        <ContestFormat>1</ContestFormat><ContestsRedraftPeriod>-1</ContestsRedraftPeriod>
        <AllowApplication>1</AllowApplication><MaxParticipants>9</MaxParticipants>
        <HasPassword>1</HasPassword><AllowParticipantMatchValidation>0</AllowParticipantMatchValidation>
        <AutomaticAdvancement>0</AutomaticAdvancement><AllowTeamCreation>1</AllowTeamCreation>
        <TimerId>6</TimerId><AllowExperiencedTeams>1</AllowExperiencedTeams>
        <AllowCustomTeams>0</AllowCustomTeams><Format>2</Format>
        <RedraftOnCompetitionEnd>0</RedraftOnCompetitionEnd><AllowTicketOffer>1</AllowTicketOffer>
        <EnableRanking>1</EnableRanking><AccumulateTreasuryForRedraft>0</AccumulateTreasuryForRedraft>
        <RedraftTreasuryCap>1300000</RedraftTreasuryCap><AdmissionMode>1</AdmissionMode>
        <AllowTicketRequest>1</AllowTicketRequest><AutomaticValidation>1</AutomaticValidation>
        <EnableMatchConsequences>1</EnableMatchConsequences><AllowAiTeams>1</AllowAiTeams>
        <BannedSpecialCards/><BannedPitches/>
        </Setting></ResponseGetCompetitionSetting>"""
    )
    setting = CompetitionSetting.from_response(root)
    assert setting.max_participants == 9
    assert setting.timer_id == 6
    assert setting.redraft_treasury_cap == 1_300_000
    assert setting.enable_match_consequences is True
    assert setting.allow_custom_teams is False


def test_schedule_model():
    root = ET.fromstring(
        f"""<ResponseGetCompetitionSchedule>
        <Schedule><Contest><Matches><Match>
          <Status>3</Status><GameId>{b64('game-1')}</GameId>
          <HomeScore>2</HomeScore><AwayScore>1</AwayScore>
          <HomeTeam><Id>{b64('team-h')}</Id><Name>{b64('Home')}</Name><Race>1</Race><Value>1000000</Value></HomeTeam>
          <AwayTeam><Id>{b64('team-a')}</Id><Name>{b64('Away')}</Name><Race>2</Race><Value>1100000</Value></AwayTeam>
          <HomeGamer><Id>{b64('gamer-h')}</Id><Name>{b64('Coach H')}</Name></HomeGamer>
          <AwayGamer><Id>{b64('gamer-a')}</Id><Name>{b64('Coach A')}</Name></AwayGamer>
          <Id>{b64('match-1')}</Id>
        </Match></Matches><Id>{b64('contest-1')}</Id><Format>1</Format></Contest></Schedule>
        <Day>9</Day>
        <Competition><Id>{b64('competition-1')}</Id><Name>{b64('League day')}</Name>
          <SettingId>{b64('setting-1')}</SettingId><LeagueId>{b64('league-1')}</LeagueId>
          <Day>9</Day><Format>2</Format><Status>4</Status><IsCrossPlay>1</IsCrossPlay>
        </Competition>
        </ResponseGetCompetitionSchedule>"""
    )
    schedule = CompetitionSchedule.from_response(root)
    assert schedule.day == 9
    assert schedule.competition.competition_id == "competition-1"
    match = schedule.contests[0].matches[0]
    assert match.game_id == "game-1"
    assert match.home_score == 2
    assert match.away_team.name == "Away"


def test_game_list_and_result_models():
    games_root = ET.fromstring(
        f"""<ResponseGetGames><Total>1</Total><Games><GameData>
        <GameId>{b64('game-1')}</GameId><MatchId>{b64('match-1')}</MatchId>
        <HomeScore>2</HomeScore><AwayScore>0</AwayScore>
        <HomeValidation>1</HomeValidation><AwayValidation>0</AwayValidation>
        <HasPendingValidation>0</HasPendingValidation>
        <HomeTeam><Id>{b64('team-h')}</Id><Name>{b64('Home')}</Name></HomeTeam>
        <AwayTeam><Id>{b64('team-a')}</Id><Name>{b64('Away')}</Name></AwayTeam>
        </GameData></Games></ResponseGetGames>"""
    )
    games = GameList.from_response(games_root)
    assert games.total == 1
    assert games.games[0].game_id == "game-1"
    assert games.games[0].home_score == 2

    result_root = ET.fromstring(
        f"""<ResponseGetGameResult><GameResult>
        <GameId>{b64('game-1')}</GameId><MatchId>{b64('match-1')}</MatchId>
        <HomeScore>2</HomeScore><AwayScore>0</AwayScore><HasReplay>1</HasReplay>
        <IsLive>0</IsLive><HasPendingValidation>0</HasPendingValidation>
        <HomeHasConceded>0</HomeHasConceded><AwayHasConceded>0</AwayHasConceded>
        <HomeValidation>1</HomeValidation><AwayValidation>1</AwayValidation>
        <HomeLadderGameGain><OldRating>1000</OldRating><NewRating>1010</NewRating>
          <OldDivision>1</OldDivision><NewDivision>1</NewDivision></HomeLadderGameGain>
        <HomeGameResultGain><PreviousTreasury>100000</PreviousTreasury><NewTreasury>140000</NewTreasury>
          <PreviousDedicatedFans>3</PreviousDedicatedFans><NewDedicatedFans>4</NewDedicatedFans>
          <DedicatedFansRoll>6</DedicatedFansRoll><FanAttendance>5000</FanAttendance>
          <CashSpentDuringMatch>0</CashSpentDuringMatch></HomeGameResultGain>
        </GameResult></ResponseGetGameResult>"""
    )
    result = GameResult.from_response(result_root)
    assert result.game_id == "game-1"
    assert result.has_replay is True
    assert result.home_ladder_gain.new_rating == 1010
    assert result.home_result_gain.new_treasury == 140000


def test_match_statistics_decodes_labels_and_values():
    root = ET.fromstring(
        f"""<ResponseGetMatchStatistics><MatchStatistics>
        <HomeGamerStatistics><TeamStatistics><Statistics><Statistic>
          <IsHighlight>0</IsHighlight><CategoryName>{b64('Damages')}</CategoryName>
          <Value>{b64('2')}</Value><Id>19</Id><CategoryId>2</CategoryId>
          <Name>{b64('Inflicted Casualties')}</Name>
        </Statistic></Statistics>
        <Team><Id>{b64('team-h')}</Id><Name>{b64('Home')}</Name></Team>
        </TeamStatistics><Gamer><Id>{b64('gamer-h')}</Id><Name>{b64('Coach')}</Name></Gamer>
        </HomeGamerStatistics></MatchStatistics></ResponseGetMatchStatistics>"""
    )
    stats = MatchStatistics.from_response(root)
    item = stats.home.statistics[0]
    assert item.statistic_id == 19
    assert item.category_name == "Damages"
    assert item.name == "Inflicted Casualties"
    assert item.value == 2
