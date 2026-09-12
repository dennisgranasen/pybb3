"""Capture-verified BB3 protocol enum values.

Only values whose meaning was directly shown by the official client are named
here. Unknown numeric fields deliberately remain plain integers elsewhere.
"""

from enum import IntEnum


class CompetitionFormat(IntEnum):
    KNOCK_OUT = 1
    ROUND_ROBIN = 2
    WISSEN = 3


class AdmissionMode(IntEnum):
    FREE = 1
    TICKETS = 2
    INVITATION_ONLY = 3


class TimerId(IntEnum):
    # TimerId 1 was displayed as "Competitive", but its precise timing rules
    # were not present in the capture and are therefore not named here.
    STRICT_ONE_MINUTE = 2
    UNLIMITED = 6


class CompetitionStatus(IntEnum):
    CREATED = 1


class LeagueRole(IntEnum):
    ADMIN = 3
    MEMBER = 4


class BoardPermission(IntEnum):
    CAN_UPDATE_SETTING = 8
    CAN_READ_LEAGUE_TICKETS = 16
    CAN_OFFER_LEAGUE_TICKET = 17
    CAN_ACCEPT_LEAGUE_TICKET = 18
    CAN_DELETE_LEAGUE_TICKET = 19
    CAN_REFUSE_LEAGUE_TICKET = 20
    CAN_UPDATE_LEAGUE_SETTING = 21
    CAN_END_LEAGUE = 22
    CAN_KICK_LEAGUE_MEMBER = 23
    CAN_CREATE_LEAGUE_COMPETITION = 24
    CAN_GET_LEAGUE_MEMBERS = 25
    CAN_MANAGE_LEAGUE_NEWS = 26
    CAN_GET_LEAGUE_NEWS = 27


# Replay enums below are corroborated by the independent ZFLStats BB3 parser.
class BlockOutcome(IntEnum):
    ATTACKER_DOWN = 0
    BOTH_DOWN = 1
    BOTH_WRESTLE_DOWN = 2
    BOTH_STANDING = 3
    PUSHED = 4
    DEFENDER_DOWN = 5
    DEFENDER_PUSHED_DOWN = 6


class InjuryOutcome(IntEnum):
    STUNNED = 0
    RESERVE = 1
    KO = 2
    BADLY_HURT = 3
    CASUALTY = 4


class CasualtyOutcome(IntEnum):
    NO_CASUALTY = 0
    BADLY_HURT = 1
    SERIOUSLY_HURT = 2
    SERIOUS_INJURY = 3
    LASTING_INJURY = 4
    SMASHED_KNEE = 5
    HEAD_INJURY = 6
    BROKEN_ARM = 7
    NECK_INJURY = 8
    DISLOCATED_SHOULDER = 9
    DEAD = 10


class PlayerSituation(IntEnum):
    PITCH = 0
    RESERVE = 1
    KO = 2
    INJURED = 4
    EXPELLED = 5


class PlayerStatus(IntEnum):
    STANDING = 0
    PRONE = 1
    STUNNED = 2
    KO = 3
    INJURED = 4
    DEAD = 5
    EXPELLED = 6
    HEAT_STROKE = 7


class SequenceType(IntEnum):
    NO_ACTIVATION = 0
    MOVE = 1
    BLOCK = 2
    BLITZ = 3
    PASS = 4
    HANDOFF = 5
    FOUL = 6
    THROW_TEAM_MATE = 7
    ON_THE_BALL = 8
    DUMP_OFF = 9
    TENTACLES = 10
    SHADOWING = 11
    TREACHEROUS_TRAP = 12
    KICK_OFF = 13


class StepType(IntEnum):
    ACTIVATION = 0
    MOVE = 1
    DAMAGE = 2
    BALL = 3
    CATCH = 4
    HANDOFF = 5
    BLOCK = 6
    STAND_UP = 7
    FOUL = 8
    REFEREE = 9
    KICKOFF = 10
    PASS = 11
    JUMP_OVER = 12
    THROW_TEAM_MATE = 13
    LAND = 14
    BOUNCE_PLAYER = 15
    STAB = 16
    VOMIT = 17
    DIVING_CATCH = 18
    FIREBALL = 19
    ZAP = 20
    TREACHEROUS_TRAP = 21
    GEYSER = 22
    HYPNOTIC_GAZE = 23
    CHAINSAW = 24
    CHAINSAW_FOUL = 25
    TENTACLES = 26
    SHADOWING = 27
    THROW_A_ROCK = 28
    INTERCEPTION = 29
    MULTIPLE_BLOCK = 30
    BLOODLUST_BITE = 34


class RollType(IntEnum):
    NO_ROLL = 0
    GFI = 1
    DODGE = 2
    BLOCK = 3
    PICK_UP = 4
    PASS = 5
    INTERCEPTION = 6
    CATCH = 7
    SCATTER = 8
    THROW_IN = 9
    ARMOR = 10
    INJURY = 11
    CASUALTY = 12
    WAKE_UP = 13
    HALFLING_CHEF = 14
    PRO = 15
    TENTACLES = 16
    SCATTER_PLAYER = 17
    SWELTERING_HEAT = 18
    PENALTY_SHOTS = 19
    STAND_UP = 20
    BRIBE = 21
    BRILLIANT_COACHING = 22
    FAN_FACTOR = 23
    WEATHER = 24
    BOUNCE = 25
    DEVIATE = 26
    TOUCHBACK = 27
    BAD_HABITS = 28
    JUMP_OVER = 29
    ARGUE_THE_CALL = 30
    DAUNTLESS = 31
    JUMP_UP = 32
    BONE_HEAD = 33
    REALLY_STUPID = 34
    UNCHANNELLED_FURY = 35
    ANIMAL_SAVAGERY = 36
    FOUL_APPEARANCE = 37
    SEISMIC_ACTIVITY_TRIGGER = 38
    UNSTUN = 39
    GEYSER = 40
    THROW_TEAM_MATE = 41
    LAND = 42
    ALWAYS_HUNGRY = 43
    ESCAPE_TEAM_MATE = 44
    VOMIT_ACCURACY = 45
    REGENERATION = 46
    FIREBALL_HIT = 48
    THUNDERBOLT_HIT = 49
    STRANGE_FAUNA_HIT = 50
    ZAP = 51
    KICK_OFF_TABLE = 52
    BRAWLER = 57
    LASTING_INJURY = 58
    PITCH_INVASION = 59
    HYPNOTIC_GAZE = 66
    CHAINSAW = 67
    TAKE_ROOT = 68
    LONER = 71
    SHADOWING = 73
    ANIMOSITY = 74
    SWARMING = 75
    BLOODLUST = 96


class SpecialCard(IntEnum):
    FRIENDLY_FANS = 3
    SPRINKLER_MALFUNCTION = 5
    JOHNNY_WATERBOY = 6
    HECKLER = 7
    ROWDY_FANS = 8
    EVERYONES_AN_EXPERT = 9
    EXPERIMENTAL_FOOTGEAR = 12
    THE_PROTEGE = 13
    BAD_BURGER = 14
    ASSASSINATION_ATTEMPT = 15
    FOR_WHOM_THE_BELL_TOLLS = 16
    WARPSTONE_DUST = 17
    RAT_RACE = 18
    THE_MUSK_OF_FEAR = 19
    SHAMANIC_JUJU = 21
    STUBBORN_DETERMINATION = 26
    BAD_HABITS = 31
    STEELHELMS_SPORTING_TONIC = 44
    FUNGUS_BREW = 52
    MARTIAL_TRAINING = 56
    WHISPERED_SECRETS = 71
    SIDELINE_INTERFERENCE = 73
    PRE_MATCH_ESPIONAGE = 82
    HIDDEN_BLADE = 85
    SPECTACULAR_CATCH = 89
    BURST_OF_SPEED = 97
    ALL_OUT_BLITZ = 140
    WEATHER_MAGE = 252
    FIREBALL = 253
    ZAP = 254
