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
