from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import xml.etree.ElementTree as ET

from .encoding import b64_decode_text


def _int(element: ET.Element | None, path: str, default: int = 0) -> int:
    text = element.findtext(path) if element is not None else None
    try:
        return int(text) if text not in (None, "") else default
    except ValueError:
        return default


def _optional_int(element: ET.Element | None, path: str) -> int | None:
    text = element.findtext(path) if element is not None else None
    if text in (None, ""):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _bool(element: ET.Element | None, path: str, default: bool = False) -> bool:
    text = element.findtext(path) if element is not None else None
    if text is None:
        return default
    return text.strip().lower() in {"1", "true", "yes"}


def _b64(element: ET.Element | None, path: str) -> str | None:
    text = element.findtext(path) if element is not None else None
    if not text:
        return None
    try:
        return b64_decode_text(text)
    except Exception:
        # Keep protocol parsing forward-compatible if a field that normally
        # contains Base64 is temporarily emitted as plain text.
        return text


def _b64_int(element: ET.Element | None, path: str, default: int = 0) -> int:
    text = _b64(element, path)
    try:
        return int(text) if text not in (None, "") else default
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Formation:
    team_id: str
    name: str
    formation_type: int
    pitch_map: dict[str, dict[str, int]]
    formation_id: str | None = None

    def data_dict(self) -> dict[str, Any]:
        return {"pitchMap": self.pitch_map}


@dataclass(slots=True)
class CollectionItem:
    item_id: str
    label: str | None = None
    behaviour: str | None = None
    instance_ids: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class PlayerCharacteristic:
    characteristic_id: int
    value: int
    bonuses: int = 0
    maluses: int = 0


@dataclass(slots=True, frozen=True)
class PlayerSkillOption:
    skill_id: int
    available: bool
    choosable: bool
    cost: int
    team_value: int


@dataclass(slots=True, frozen=True)
class PlayerSkillCategory:
    category: int
    affinity: int
    cost_random: int
    team_value_random: int
    team_value_chosen: int
    random_available: bool
    random_choosable: bool
    skills: tuple[PlayerSkillOption, ...] = ()


@dataclass(slots=True)
class Player:
    player_id: str | None
    ugc_id: str | None
    name: str | None
    position_id: int
    number: int
    slot_number: int | None
    level: int
    spp: int
    level_up_status: int
    value: int
    dead: bool
    miss_next_game: bool
    retirement_status: int
    can_be_updated: bool
    has_original_name: bool
    skill_ids: tuple[int, ...]
    characteristics: tuple[PlayerCharacteristic, ...]
    casualty_ids: tuple[int, ...]
    raw_xml: str


@dataclass(slots=True)
class RosterPosition:
    position_id: int
    cost: int
    maximum: int
    starting_skill_ids: tuple[int, ...]
    characteristics: tuple[PlayerCharacteristic, ...]
    skill_categories: tuple[PlayerSkillCategory, ...]
    raw_xml: str


@dataclass(slots=True, frozen=True)
class RosterizedInducement:
    inducement_id: int
    number: int
    available: bool
    maximum: int
    cost: int
    original_cost: int


@dataclass(slots=True)
class TeamRoster:
    can_add_starplayer: bool
    can_be_redrafted: bool
    nb_slots: int
    can_be_updated_reason: str | None
    players: tuple[Player, ...]
    positions: tuple[RosterPosition, ...]
    rosterized_inducements: tuple[RosterizedInducement, ...]
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "TeamRoster":
        roster = root.find("Roster")
        if roster is None:
            raise ValueError("ResponseGetTeamRoster contained no Roster")

        positions = tuple(
            _parse_roster_position(line)
            for line in roster.findall(
                "./RaceRoster/Slots/RosterSlot/Lines/RosterSlotLine"
            )
        )

        players = tuple(
            _parse_player(slot.find("Player"), slot_number=_int(slot, "Number"))
            for slot in roster.findall("./TeamRoster/TeamRosterSlot")
            if slot.find("Player") is not None
        )

        inducements: list[RosterizedInducement] = []
        for item in roster.findall("./RosterizedInducements/RosterizedInducement"):
            inducement = item.find("Inducement")
            if inducement is None:
                continue
            inducements.append(
                RosterizedInducement(
                    inducement_id=_int(inducement, "Id"),
                    number=_int(item, "Number"),
                    available=_bool(inducement, "Available"),
                    maximum=_int(inducement, "Max"),
                    cost=_int(inducement, "Cost"),
                    original_cost=_int(inducement, "OriginalCost"),
                )
            )

        return cls(
            can_add_starplayer=_bool(roster, "CanAddStarplayer"),
            can_be_redrafted=_bool(roster, "CanBeRedrafted"),
            nb_slots=_int(roster, "Nb_slots"),
            can_be_updated_reason=roster.findtext("CanBeUpdatedReason") or None,
            players=players,
            positions=positions,
            rosterized_inducements=tuple(inducements),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


@dataclass(slots=True)
class PlayerImprovements:
    skill_categories: tuple[PlayerSkillCategory, ...]
    characteristic_available: bool
    characteristic_choosable: bool
    characteristic_cost: int
    spent_spp: int
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "PlayerImprovements":
        return cls(
            skill_categories=tuple(
                _parse_skill_category(category)
                for category in root.findall("./SkillCategories/PlayerSkillCategory")
            ),
            characteristic_available=_bool(root, "IsCharacteristicAvailable"),
            characteristic_choosable=_bool(root, "IsCharacteristicChoosable"),
            characteristic_cost=_int(root, "CharacteristicCost"),
            spent_spp=_int(root, "SpentSpp"),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


@dataclass(slots=True, frozen=True)
class RandomSkillResult:
    skill_id: int
    has_left: bool


@dataclass(slots=True, frozen=True)
class CharacteristicUpgrade:
    characteristic_id: int
    available: bool
    team_value: int
    message: str | None = None


@dataclass(slots=True)
class CharacteristicRoll:
    roll: int
    can_take_secondary_skill: bool
    characteristics: tuple[CharacteristicUpgrade, ...]
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "CharacteristicRoll":
        upgrades = tuple(
            CharacteristicUpgrade(
                characteristic_id=_int(item, "Id"),
                available=_bool(item, "Available"),
                team_value=_int(item, "TeamValue"),
                message=item.findtext("Message") or None,
            )
            for item in root.findall("./Characteristics/CharacteristicUpgrade")
        )
        return cls(
            roll=_int(root, "Roll"),
            can_take_secondary_skill=_bool(root, "CanTakeSecondarySkill"),
            characteristics=upgrades,
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


# ---------- Competition / game models ----------

@dataclass(slots=True, frozen=True)
class GamerSummary:
    gamer_id: str | None
    name: str | None


@dataclass(slots=True, frozen=True)
class TeamSummary:
    team_id: str | None
    name: str | None
    race_id: int | None
    value: int | None


@dataclass(slots=True)
class Competition:
    competition_id: str | None
    name: str | None
    setting_id: str | None
    league_id: str | None
    day: int
    format: int
    status: int
    is_official: bool
    is_eternal: bool
    allow_team_registration: bool
    has_divisions: bool
    is_cross_play: bool
    raw_xml: str

    @classmethod
    def from_element(cls, competition: ET.Element) -> "Competition":
        return cls(
            competition_id=_b64(competition, "Id"),
            name=_b64(competition, "Name"),
            setting_id=_b64(competition, "SettingId"),
            league_id=_b64(competition, "LeagueId"),
            day=_int(competition, "Day"),
            format=_int(competition, "Format"),
            status=_int(competition, "Status"),
            is_official=_bool(competition, "IsOfficial"),
            is_eternal=_bool(competition, "IsEternal"),
            allow_team_registration=_bool(competition, "AllowTeamRegistration"),
            has_divisions=_bool(competition, "HasDivisions"),
            is_cross_play=_bool(competition, "IsCrossPlay"),
            raw_xml=ET.tostring(competition, encoding="unicode"),
        )

    @classmethod
    def from_response(cls, root: ET.Element) -> "Competition":
        competition = root.find("Competition")
        if competition is None:
            raise ValueError(f"{root.tag} contained no Competition")
        return cls.from_element(competition)


@dataclass(slots=True)
class CompetitionSetting:
    redraft_on_team_registration: bool
    contest_format: int
    contests_redraft_period: int
    allow_application: bool
    max_participants: int
    has_password: bool
    allow_participant_match_validation: bool
    automatic_advancement: bool
    allow_team_creation: bool
    timer_id: int
    allow_experienced_teams: bool
    allow_custom_teams: bool
    format: int
    redraft_on_competition_end: bool
    allow_ticket_offer: bool
    enable_ranking: bool
    accumulate_treasury_for_redraft: bool
    redraft_treasury_cap: int
    admission_mode: int
    allow_ticket_request: bool
    automatic_validation: bool
    enable_match_consequences: bool
    allow_ai_teams: bool
    banned_special_cards_raw: str | None
    banned_pitches_raw: str | None
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "CompetitionSetting":
        setting = root.find("Setting")
        if setting is None:
            raise ValueError("ResponseGetCompetitionSetting contained no Setting")
        return cls(
            redraft_on_team_registration=_bool(setting, "RedraftOnTeamRegistration"),
            contest_format=_int(setting, "ContestFormat"),
            contests_redraft_period=_int(setting, "ContestsRedraftPeriod"),
            allow_application=_bool(setting, "AllowApplication"),
            max_participants=_int(setting, "MaxParticipants"),
            has_password=_bool(setting, "HasPassword"),
            allow_participant_match_validation=_bool(
                setting, "AllowParticipantMatchValidation"
            ),
            automatic_advancement=_bool(setting, "AutomaticAdvancement"),
            allow_team_creation=_bool(setting, "AllowTeamCreation"),
            timer_id=_int(setting, "TimerId"),
            allow_experienced_teams=_bool(setting, "AllowExperiencedTeams"),
            allow_custom_teams=_bool(setting, "AllowCustomTeams"),
            format=_int(setting, "Format"),
            redraft_on_competition_end=_bool(setting, "RedraftOnCompetitionEnd"),
            allow_ticket_offer=_bool(setting, "AllowTicketOffer"),
            enable_ranking=_bool(setting, "EnableRanking"),
            accumulate_treasury_for_redraft=_bool(
                setting, "AccumulateTreasuryForRedraft"
            ),
            redraft_treasury_cap=_int(setting, "RedraftTreasuryCap"),
            admission_mode=_int(setting, "AdmissionMode"),
            allow_ticket_request=_bool(setting, "AllowTicketRequest"),
            automatic_validation=_bool(setting, "AutomaticValidation"),
            enable_match_consequences=_bool(setting, "EnableMatchConsequences"),
            allow_ai_teams=_bool(setting, "AllowAiTeams"),
            banned_special_cards_raw=setting.findtext("BannedSpecialCards"),
            banned_pitches_raw=setting.findtext("BannedPitches"),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


@dataclass(slots=True, frozen=True)
class CompetitionMatch:
    match_id: str | None
    game_id: str | None
    status: int
    home_score: int
    away_score: int
    home_team: TeamSummary | None
    away_team: TeamSummary | None
    home_gamer: GamerSummary | None
    away_gamer: GamerSummary | None


@dataclass(slots=True, frozen=True)
class CompetitionContest:
    contest_id: str | None
    format: int
    matches: tuple[CompetitionMatch, ...]


@dataclass(slots=True)
class CompetitionSchedule:
    day: int
    competition: Competition | None
    contests: tuple[CompetitionContest, ...]
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "CompetitionSchedule":
        contests = []
        for contest in root.findall("./Schedule/Contest"):
            matches = tuple(
                _parse_competition_match(match)
                for match in contest.findall("./Matches/Match")
            )
            contests.append(
                CompetitionContest(
                    contest_id=_b64(contest, "Id"),
                    format=_int(contest, "Format"),
                    matches=matches,
                )
            )
        competition_element = root.find("Competition")
        return cls(
            day=_int(root, "Day"),
            competition=(
                Competition.from_element(competition_element)
                if competition_element is not None
                else None
            ),
            contests=tuple(contests),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


@dataclass(slots=True, frozen=True)
class GameData:
    game_id: str | None
    match_id: str | None
    home_score: int
    away_score: int
    home_validation: int
    away_validation: int
    has_pending_validation: bool
    home_team: TeamSummary | None
    away_team: TeamSummary | None
    home_gamer: GamerSummary | None
    away_gamer: GamerSummary | None
    competition: Competition | None


@dataclass(slots=True)
class GameList:
    total: int
    games: tuple[GameData, ...]
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "GameList":
        return cls(
            total=_int(root, "Total"),
            games=tuple(_parse_game_data(game) for game in root.findall("./Games/GameData")),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


@dataclass(slots=True, frozen=True)
class LadderGameGain:
    old_rating: int
    new_rating: int
    old_division: int
    new_division: int


@dataclass(slots=True, frozen=True)
class TeamGameResultGain:
    previous_treasury: int
    new_treasury: int
    previous_dedicated_fans: int
    new_dedicated_fans: int
    dedicated_fans_roll: int
    fan_attendance: int
    cash_spent_during_match: int


@dataclass(slots=True)
class GameResult:
    game_id: str | None
    match_id: str | None
    home_score: int
    away_score: int
    has_replay: bool
    is_live: bool
    has_pending_validation: bool
    home_has_conceded: bool
    away_has_conceded: bool
    home_validation: int
    away_validation: int
    home_team: TeamSummary | None
    away_team: TeamSummary | None
    home_gamer: GamerSummary | None
    away_gamer: GamerSummary | None
    competition: Competition | None
    home_ladder_gain: LadderGameGain | None
    away_ladder_gain: LadderGameGain | None
    home_result_gain: TeamGameResultGain | None
    away_result_gain: TeamGameResultGain | None
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "GameResult":
        result = root.find("GameResult")
        if result is None:
            raise ValueError("ResponseGetGameResult contained no GameResult")
        competition_element = result.find("Competition")
        return cls(
            game_id=_b64(result, "GameId"),
            match_id=_b64(result, "MatchId"),
            home_score=_int(result, "HomeScore"),
            away_score=_int(result, "AwayScore"),
            has_replay=_bool(result, "HasReplay"),
            is_live=_bool(result, "IsLive"),
            has_pending_validation=_bool(result, "HasPendingValidation"),
            home_has_conceded=_bool(result, "HomeHasConceded"),
            away_has_conceded=_bool(result, "AwayHasConceded"),
            home_validation=_int(result, "HomeValidation"),
            away_validation=_int(result, "AwayValidation"),
            home_team=_parse_team_summary(result.find("HomeTeam")),
            away_team=_parse_team_summary(result.find("AwayTeam")),
            home_gamer=_parse_gamer_summary(result.find("HomeGamer")),
            away_gamer=_parse_gamer_summary(result.find("AwayGamer")),
            competition=(
                Competition.from_element(competition_element)
                if competition_element is not None
                else None
            ),
            home_ladder_gain=_parse_ladder_gain(result.find("HomeLadderGameGain")),
            away_ladder_gain=_parse_ladder_gain(result.find("AwayLadderGameGain")),
            home_result_gain=_parse_team_game_result_gain(
                result.find("HomeGameResultGain")
            ),
            away_result_gain=_parse_team_game_result_gain(
                result.find("AwayGameResultGain")
            ),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


@dataclass(slots=True, frozen=True)
class Statistic:
    statistic_id: int
    category_id: int
    category_name: str | None
    name: str | None
    value_text: str | None
    value: int | None
    is_highlight: bool


@dataclass(slots=True, frozen=True)
class GamerMatchStatistics:
    gamer: GamerSummary | None
    team: TeamSummary | None
    statistics: tuple[Statistic, ...]


@dataclass(slots=True)
class MatchStatistics:
    home: GamerMatchStatistics | None
    away: GamerMatchStatistics | None
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "MatchStatistics":
        stats = root.find("MatchStatistics")
        if stats is None:
            raise ValueError("ResponseGetMatchStatistics contained no MatchStatistics")
        return cls(
            home=_parse_gamer_match_statistics(stats.find("HomeGamerStatistics")),
            away=_parse_gamer_match_statistics(stats.find("AwayGamerStatistics")),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


def _parse_characteristics(parent: ET.Element | None) -> tuple[PlayerCharacteristic, ...]:
    if parent is None:
        return ()
    return tuple(
        PlayerCharacteristic(
            characteristic_id=_int(item, "Characteristic"),
            value=_int(item, "Value"),
            bonuses=_int(item, "NbBonuses"),
            maluses=_int(item, "NbMaluses"),
        )
        for item in parent.findall("./PlayerCharacteristicsEntry")
    )


def _parse_skill_category(category: ET.Element) -> PlayerSkillCategory:
    skills = tuple(
        PlayerSkillOption(
            skill_id=_int(skill, "SkillId"),
            available=_bool(skill, "IsAvailable"),
            choosable=_bool(skill, "IsChoosable"),
            cost=_int(skill, "Cost"),
            team_value=_int(skill, "TeamValue"),
        )
        for skill in category.findall("./Skills/PlayerSkill")
    )
    return PlayerSkillCategory(
        category=_int(category, "Category"),
        affinity=_int(category, "Affinity"),
        cost_random=_int(category, "CostRandom"),
        team_value_random=_int(category, "TeamValueRandom"),
        team_value_chosen=_int(category, "TeamValueChosen"),
        random_available=_bool(category, "IsRandomAvailable"),
        random_choosable=_bool(category, "IsRandomChoosable"),
        skills=skills,
    )


def _parse_player(player: ET.Element | None, *, slot_number: int | None) -> Player:
    if player is None:
        raise ValueError("TeamRosterSlot contained no Player")
    casualties: list[int] = []
    for item in player.findall("./Casualties/*"):
        try:
            casualties.append(int(item.text or ""))
        except ValueError:
            continue

    return Player(
        player_id=_b64(player, "Id"),
        ugc_id=_b64(player, "UgcId"),
        name=_b64(player, "Name"),
        position_id=_int(player, "Position"),
        number=_int(player, "Number"),
        slot_number=slot_number,
        level=_int(player, "Level"),
        spp=_int(player, "Spp"),
        level_up_status=_int(player, "LevelUpStatus"),
        value=_int(player, "Value"),
        dead=_bool(player, "Dead"),
        miss_next_game=_bool(player, "MissNextGame"),
        retirement_status=_int(player, "RetirementStatus"),
        can_be_updated=_bool(player, "CanBeUpdated"),
        has_original_name=_bool(player, "HasOriginalName"),
        skill_ids=tuple(
            int(item.text)
            for item in player.findall("./Skills/SkillsItem")
            if item.text and item.text.isdigit()
        ),
        characteristics=_parse_characteristics(player.find("Characteristics")),
        casualty_ids=tuple(casualties),
        raw_xml=ET.tostring(player, encoding="unicode"),
    )


def _parse_roster_position(line: ET.Element) -> RosterPosition:
    template = line.find("Player")
    return RosterPosition(
        position_id=_int(line, "Position"),
        cost=_int(line, "Cost"),
        maximum=_int(line, "Max"),
        starting_skill_ids=tuple(
            int(item.text)
            for item in line.findall("./Player/Skills/SkillsItem")
            if item.text and item.text.isdigit()
        ),
        characteristics=_parse_characteristics(
            template.find("Characteristics") if template is not None else None
        ),
        skill_categories=tuple(
            _parse_skill_category(category)
            for category in line.findall("./SkillsCategories/PlayerSkillCategory")
        ),
        raw_xml=ET.tostring(line, encoding="unicode"),
    )


def _parse_gamer_summary(gamer: ET.Element | None) -> GamerSummary | None:
    if gamer is None:
        return None
    return GamerSummary(
        gamer_id=_b64(gamer, "Id"),
        name=_b64(gamer, "Name"),
    )


def _parse_team_summary(team: ET.Element | None) -> TeamSummary | None:
    if team is None:
        return None
    return TeamSummary(
        team_id=_b64(team, "Id"),
        name=_b64(team, "Name"),
        race_id=_optional_int(team, "Race"),
        value=_optional_int(team, "Value"),
    )


def _parse_competition_match(match: ET.Element) -> CompetitionMatch:
    return CompetitionMatch(
        match_id=_b64(match, "Id"),
        game_id=_b64(match, "GameId"),
        status=_int(match, "Status"),
        home_score=_int(match, "HomeScore"),
        away_score=_int(match, "AwayScore"),
        home_team=_parse_team_summary(match.find("HomeTeam")),
        away_team=_parse_team_summary(match.find("AwayTeam")),
        home_gamer=_parse_gamer_summary(match.find("HomeGamer")),
        away_gamer=_parse_gamer_summary(match.find("AwayGamer")),
    )


def _parse_game_data(game: ET.Element) -> GameData:
    competition_element = game.find("Competition")
    return GameData(
        game_id=_b64(game, "GameId"),
        match_id=_b64(game, "MatchId"),
        home_score=_int(game, "HomeScore"),
        away_score=_int(game, "AwayScore"),
        home_validation=_int(game, "HomeValidation"),
        away_validation=_int(game, "AwayValidation"),
        has_pending_validation=_bool(game, "HasPendingValidation"),
        home_team=_parse_team_summary(game.find("HomeTeam")),
        away_team=_parse_team_summary(game.find("AwayTeam")),
        home_gamer=_parse_gamer_summary(game.find("HomeGamer")),
        away_gamer=_parse_gamer_summary(game.find("AwayGamer")),
        competition=(
            Competition.from_element(competition_element)
            if competition_element is not None
            else None
        ),
    )


def _parse_ladder_gain(element: ET.Element | None) -> LadderGameGain | None:
    if element is None:
        return None
    return LadderGameGain(
        old_rating=_int(element, "OldRating"),
        new_rating=_int(element, "NewRating"),
        old_division=_int(element, "OldDivision"),
        new_division=_int(element, "NewDivision"),
    )


def _parse_team_game_result_gain(
    element: ET.Element | None,
) -> TeamGameResultGain | None:
    if element is None:
        return None
    return TeamGameResultGain(
        previous_treasury=_int(element, "PreviousTreasury"),
        new_treasury=_int(element, "NewTreasury"),
        previous_dedicated_fans=_int(element, "PreviousDedicatedFans"),
        new_dedicated_fans=_int(element, "NewDedicatedFans"),
        dedicated_fans_roll=_int(element, "DedicatedFansRoll"),
        fan_attendance=_int(element, "FanAttendance"),
        cash_spent_during_match=_int(element, "CashSpentDuringMatch"),
    )


def _parse_statistic(item: ET.Element) -> Statistic:
    value_text = _b64(item, "Value")
    try:
        value = int(value_text) if value_text not in (None, "") else None
    except ValueError:
        value = None
    return Statistic(
        statistic_id=_int(item, "Id"),
        category_id=_int(item, "CategoryId"),
        category_name=_b64(item, "CategoryName"),
        name=_b64(item, "Name"),
        value_text=value_text,
        value=value,
        is_highlight=_bool(item, "IsHighlight"),
    )


def _parse_gamer_match_statistics(
    element: ET.Element | None,
) -> GamerMatchStatistics | None:
    if element is None:
        return None
    team_statistics = element.find("TeamStatistics")
    statistics = (
        tuple(
            _parse_statistic(item)
            for item in team_statistics.findall("./Statistics/Statistic")
        )
        if team_statistics is not None
        else ()
    )
    return GamerMatchStatistics(
        gamer=_parse_gamer_summary(element.find("Gamer")),
        team=_parse_team_summary(
            team_statistics.find("Team") if team_statistics is not None else None
        ),
        statistics=statistics,
    )
