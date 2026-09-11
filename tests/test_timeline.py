import base64
import json

from bb3.replay import Replay


def b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def message(name: str, xml: str) -> str:
    return f"<StringMessage><Name>{b64(name)}</Name><MessageData>{b64(b64(xml))}</MessageData></StringMessage>"


def sequence(*messages: str) -> str:
    return "<EventExecuteSequence><Sequence><StepResult><Results>" + "".join(messages) + "</Results></StepResult></Sequence></EventExecuteSequence>"


def test_multisequence_block_becomes_one_actor_target_event(tmp_path):
    step = "<PlayerStep><PlayerId>1</PlayerId><TargetId>2</TargetId><StepType>6</StepType></PlayerStep>"
    block = "<ResultBlockOutcome><AttackerId>1</AttackerId><DefenderId>2</DefenderId><Outcome>6</Outcome></ResultBlockOutcome>"
    push = "<ResultPushBack><PushedPlayerId>2</PushedPlayerId><CellFrom><X>2</X></CellFrom><CellTo><X>3</X></CellTo></ResultPushBack>"
    armour = "<ResultRoll><RollType>10</RollType><Outcome>1</Outcome></ResultRoll>"
    injury = "<ResultInjuryRoll><RollType>11</RollType><Outcome>0</Outcome></ResultInjuryRoll>"
    xml = f"""<Replay><Rosters>
      <TeamRoster><Players><PlayerData><Name>{b64('Ada')}</Name><Id>1</Id></PlayerData></Players><Name>{b64('Home')}</Name><Team><TeamId>0</TeamId></Team></TeamRoster>
      <TeamRoster><Players><PlayerData><Name>{b64('Bob')}</Name><Id>2</Id></PlayerData></Players><Name>{b64('Away')}</Name><Team><TeamId>1</TeamId></Team></TeamRoster>
    </Rosters><ReplayStep><Clock>40</Clock>{sequence(message('PlayerStep', step), message('QuestionBlockDice', '<QuestionBlockDice/>'))}</ReplayStep>
    <ReplayStep><Clock>42</Clock>{sequence(message('PlayerStep', step), message('ResultPushBack', push), message('ResultBlockOutcome', block), message('ResultRoll', armour), message('ResultInjuryRoll', injury))}
    <EventEndTurn><Reason>2</Reason></EventEndTurn><BoardState><ActiveTeam>0</ActiveTeam></BoardState></ReplayStep>
    <EndGame><Score>1</Score></EndGame></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()
    blocks = [event for event in timeline.events if event.type == "block"]
    assert len(blocks) == 1
    event = blocks[0]
    assert event.actor.name == "Ada"
    assert event.target.name == "Bob"
    assert event.outcome == "defender_pushed_down"
    assert event.source_sequences == (1, 2)
    assert [effect.type for effect in event.effects] == ["push", "knockdown", "armour_roll", "injury"]
    assert all(effect.subject.name == "Bob" for effect in event.effects)
    assert event.effects[2].outcome is True
    assert timeline.before_match["teams"][0]["name"] == "Home"
    assert timeline.after_match["Score"] == "1"
    assert timeline.save(tmp_path / "timeline.json").is_file()


def test_failed_move_assigns_injury_to_moving_player():
    step = "<PlayerStep><PlayerId>7</PlayerId><TargetId>-1</TargetId><StepType>1</StepType><CellFrom><X>1</X></CellFrom><CellTo><X>2</X></CellTo></PlayerStep>"
    move = "<ResultMoveOutcome><Moved>1</Moved></ResultMoveOutcome>"
    injury = "<ResultInjuryRoll><Outcome>0</Outcome></ResultInjuryRoll>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultMoveOutcome', move), message('ResultInjuryRoll', injury))}</ReplayStep></Replay>".encode()
    event = Replay.from_xml(xml).timeline().events[0]
    assert event.type == "move"
    assert event.actor.id == 7
    assert event.target is None
    assert event.outcome == "failed"
    assert event.effects[0].type == "injury"
    assert event.effects[0].subject.id == 7


def test_all_block_outcomes_are_named():
    expected = ["attacker_down", "both_down", "both_wrestle_down", "both_standing",
                "pushed", "defender_down", "defender_pushed_down"]
    for code, name in enumerate(expected):
        block = f"<ResultBlockOutcome><AttackerId>1</AttackerId><DefenderId>2</DefenderId><Outcome>{code}</Outcome></ResultBlockOutcome>"
        xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('ResultBlockOutcome', block))}</ReplayStep></Replay>".encode()
        assert Replay.from_xml(xml).timeline().events[0].outcome == name


def test_wizard_damage_is_linked_to_special_card():
    fireball = "<EventUseSpecialCard><GamerId>0</GamerId><CardId>253</CardId></EventUseSpecialCard>"
    damage = "<ResultPlayerRemoval><PlayerId>9</PlayerId><Situation>2</Situation><Status>3</Status></ResultPlayerRemoval>"
    xml = f"<Replay><Rosters/><ReplayStep>{fireball}{sequence(message('ResultPlayerRemoval', damage))}</ReplayStep></Replay>".encode()
    events = Replay.from_xml(xml).timeline().events
    assert events[0].type == "special_card"
    assert events[0].outcome == "fireball"
    assert events[1].type == "damage"
    assert events[1].caused_by == events[0].id
    assert events[1].effects[0].outcome == "ko"


def test_board_state_tracks_ball_possession_changes():
    xml = b"""<Replay><Rosters/>
      <ReplayStep><BoardState><Ball><IsHeld>1</IsHeld><Carrier>4</Carrier></Ball></BoardState></ReplayStep>
      <ReplayStep><BoardState><Ball><IsHeld>0</IsHeld></Ball></BoardState></ReplayStep>
    </Replay>"""
    events = Replay.from_xml(xml).timeline().events
    assert [event.type for event in events] == ["possession_gained", "ball_loose"]
    assert events[1].target.id == 4


def test_empty_active_team_means_zero_and_turn_metadata_comes_from_board():
    end = "<EventEndTurn><Reason>1</Reason></EventEndTurn>"
    board = """<BoardState><ActiveTeam/><ListTeams>
      <TeamState><GameTurn>9</GameTurn></TeamState>
      <TeamState><GameTurn>8</GameTurn></TeamState>
    </ListTeams></BoardState>"""
    playing = "<EventNewGamePhase><Phase>5</Phase></EventNewGamePhase>"
    active = "<EventActiveGamerChanged/>"
    xml = f"<Replay><Rosters/><ReplayStep>{playing}{active}{end}{board}</ReplayStep></Replay>".encode()

    turn = Replay.from_xml(xml).timeline().turns[0]

    assert turn.team_id == 0
    assert turn.half == 2
    assert turn.team_turn == 1


def test_setup_turn_does_not_leak_into_next_playing_turn():
    setup_end = "<EventEndTurn><Reason>1</Reason><FinishingTurnType>5</FinishingTurnType></EventEndTurn>"
    play_end = "<EventEndTurn><Reason>1</Reason></EventEndTurn>"
    board = """<BoardState><ActiveTeam/><ListTeams>
      <TeamState><GameTurn>1</GameTurn></TeamState><TeamState><GameTurn/></TeamState>
    </ListTeams></BoardState>"""
    playing = "<EventNewGamePhase><Phase>5</Phase></EventNewGamePhase>"
    active = "<EventActiveGamerChanged/>"
    xml = f"""<Replay><Rosters/>
      <ReplayStep>{playing}{active}<EventMatchStart/>{setup_end}{board}</ReplayStep>
      <ReplayStep>{play_end}{board}</ReplayStep>
    </Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    assert len(timeline.turns) == 1
    assert [event.type for event in timeline.turns[0].events] == ["turn_end"]
    assert any(event.type == "match_start" for event in timeline.events)


def test_match_end_transition_closes_last_turn_without_trailing_context_turn():
    active = "<EventActiveGamerChanged><NewActiveGamer>1</NewActiveGamer></EventActiveGamerChanged>"
    end = "<EventEndTurn><Reason>1</Reason><FollowingTurnType>2</FollowingTurnType></EventEndTurn>"
    board = """<BoardState><ActiveTeam>1</ActiveTeam><ListTeams>
      <TeamState><GameTurn>16</GameTurn></TeamState><TeamState><GameTurn>17</GameTurn></TeamState>
    </ListTeams></BoardState>"""
    phase = "<EventNewGamePhase><Phase>6</Phase></EventNewGamePhase>"
    xml = f"<Replay><Rosters/><ReplayStep>{active}{end}{phase}<EventMatchEnd/>{board}</ReplayStep></Replay>".encode()

    timeline = Replay.from_xml(xml).timeline()

    assert len(timeline.turns) == 1
    assert timeline.turns[0].team_id == 1
    assert [event.type for event in timeline.turns[0].events] == ["turn_end"]
    assert [event.type for event in timeline.events] == ["turn_end", "new_game_phase", "match_end"]


def test_move_keeps_action_target_as_evidence_not_recipient():
    step = "<PlayerStep><PlayerId>1</PlayerId><TargetId>2</TargetId><StepType>1</StepType></PlayerStep>"
    move = "<ResultMoveOutcome><Moved>1</Moved></ResultMoveOutcome>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultMoveOutcome', move))}</ReplayStep></Replay>".encode()

    event = Replay.from_xml(xml).timeline().events[0]

    assert event.target is None
    assert event.details["action_target"]["id"] == 2


def test_last_player_step_keeps_declared_block_with_its_result():
    activation = "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId><StepType>0</StepType></PlayerStep>"
    block_step = "<PlayerStep><PlayerId>1</PlayerId><TargetId>2</TargetId><StepType>6</StepType></PlayerStep>"
    action = "<ResultUseAction><Action>2</Action><TeamId>0</TeamId></ResultUseAction>"
    outcome = "<ResultBlockOutcome><AttackerId>1</AttackerId><DefenderId>2</DefenderId><Outcome>5</Outcome></ResultBlockOutcome>"
    xml = f"""<Replay><Rosters/><ReplayStep>
      {sequence(message('PlayerStep', activation), message('ResultUseAction', action), message('PlayerStep', block_step))}
      {sequence(message('PlayerStep', block_step), message('ResultBlockOutcome', outcome))}
    </ReplayStep></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    assert [event.type for event in timeline.events] == ["block"]
    assert timeline.events[0].details["declared_action"] == "block"
    assert not timeline.unresolved


def test_kickoff_deviation_is_classified():
    step = "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId><StepType>10</StepType><CellFrom><X>10</X><Y>7</Y></CellFrom><CellTo><X>12</X><Y>8</Y></CellTo></PlayerStep>"
    roll = "<ResultRoll><RollType>26</RollType><Dice><Die><Value>3</Value></Die></Dice><Outcome>2</Outcome></ResultRoll>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultRoll', roll))}</ReplayStep></Replay>".encode()

    timeline = Replay.from_xml(xml).timeline()

    assert timeline.events[0].type == "kickoff_deviation"
    assert timeline.events[0].details["from"] == {"X": "10", "Y": "7"}
    assert not timeline.unresolved


def test_failed_foul_appearance_prevents_declared_block():
    step = "<PlayerStep><PlayerId>39</PlayerId><TargetId>4</TargetId><StepType>0</StepType></PlayerStep>"
    action = "<ResultUseAction><Action>2</Action></ResultUseAction>"
    roll = "<ResultRoll><Requirement>2</Requirement><Dice><Die><Value>1</Value></Die></Dice><RollType>37</RollType><Outcome>0</Outcome></ResultRoll>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultUseAction', action), message('ResultRoll', roll))}</ReplayStep></Replay>".encode()

    event = Replay.from_xml(xml).timeline().events[0]

    assert event.type == "block"
    assert event.actor.id == 39 and event.target.id == 4
    assert event.outcome == "prevented"
    assert event.effects[0].type == "foul_appearance"
    assert event.effects[0].outcome == "failed"


def test_failed_animal_savagery_records_selected_teammate_and_damage():
    step = "<PlayerStep><PlayerId>37</PlayerId><TargetId>1</TargetId><StepType>0</StepType></PlayerStep>"
    action = "<ResultUseAction><Action>3</Action></ResultUseAction>"
    savagery = "<ResultRoll><Requirement>4</Requirement><Dice><Die><Value>1</Value></Die></Dice><RollType>36</RollType><Outcome>0</Outcome></ResultRoll>"
    question = "<QuestionAnimalSavagery><VictimsIds><VictimsIdsItem>46</VictimsIdsItem><VictimsIdsItem>42</VictimsIdsItem></VictimsIds></QuestionAnimalSavagery>"
    result = "<ResultAnimalSavagery><VictimId>46</VictimId></ResultAnimalSavagery>"
    armour = "<ResultRoll><Requirement>8</Requirement><Dice><Die><Value>4</Value></Die></Dice><RollType>10</RollType><Outcome>0</Outcome></ResultRoll>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultUseAction', action), message('ResultRoll', savagery), message('QuestionAnimalSavagery', question), message('ResultAnimalSavagery', result), message('ResultRoll', armour))}</ReplayStep></Replay>".encode()

    event = Replay.from_xml(xml).timeline().events[0]

    assert event.type == "animal_savagery"
    assert event.actor.id == 37 and event.target.id == 46
    assert event.outcome == "teammate_hit"
    assert event.details["declared_action"] == "blitz"
    assert event.details["action_target"]["id"] == 1
    assert [x["id"] for x in event.details["eligible_targets"]] == [46, 42]
    assert [effect.type for effect in event.effects] == ["knockdown", "armour_roll"]
    assert event.effects[1].outcome is False


def test_passed_animal_savagery_has_no_victim():
    step = "<PlayerStep><PlayerId>37</PlayerId><TargetId>10</TargetId><StepType>0</StepType></PlayerStep>"
    action = "<ResultUseAction><Action>3</Action></ResultUseAction>"
    roll = "<ResultRoll><Requirement>4</Requirement><Dice><Die><Value>5</Value></Die></Dice><RollType>36</RollType><Outcome>1</Outcome></ResultRoll>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultUseAction', action), message('ResultRoll', roll))}</ReplayStep></Replay>".encode()

    event = Replay.from_xml(xml).timeline().events[0]

    assert event.type == "animal_savagery"
    assert event.outcome == "passed"
    assert event.target is None
    assert event.details["action_target"]["id"] == 10


def test_passed_animal_savagery_is_attached_to_completed_stand_up():
    activation = "<PlayerStep><PlayerId>37</PlayerId><TargetId>-1</TargetId><StepType>0</StepType></PlayerStep>"
    stand_up = "<PlayerStep><PlayerId>37</PlayerId><TargetId>37</TargetId><StepType>7</StepType></PlayerStep>"
    action = "<ResultUseAction><Action>1</Action></ResultUseAction>"
    roll = "<ResultRoll><Requirement>4</Requirement><Dice><Die><Value>5</Value></Die></Dice><RollType>36</RollType><Outcome>1</Outcome></ResultRoll>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', activation), message('ResultUseAction', action), message('ResultRoll', roll), message('PlayerStep', stand_up))}</ReplayStep></Replay>".encode()

    event = Replay.from_xml(xml).timeline().events[0]

    assert event.type == "stand_up"
    assert event.effects[0].type == "animal_savagery"
    assert event.effects[0].outcome == "passed"


def test_narrative_export_is_compact_non_duplicated_and_keeps_context(tmp_path):
    routine_step = "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId><StepType>1</StepType></PlayerStep>"
    failed_step = "<PlayerStep><PlayerId>2</PlayerId><TargetId>-1</TargetId><StepType>1</StepType></PlayerStep>"
    move = "<ResultMoveOutcome><Moved>1</Moved></ResultMoveOutcome>"
    injury = "<ResultInjuryRoll><Outcome>0</Outcome></ResultInjuryRoll>"
    active = "<EventNewGamePhase><Phase>5</Phase></EventNewGamePhase><EventActiveGamerChanged/>"
    board = """<BoardState><ListTeams><TeamState><GameTurn>1</GameTurn></TeamState>
      <TeamState><GameTurn/></TeamState></ListTeams></BoardState>"""
    end = "<EventEndTurn><Reason>2</Reason></EventEndTurn>"
    xml = f"""<Replay><Rosters/><ReplayStep>{active}
      {sequence(message('PlayerStep', routine_step), message('ResultMoveOutcome', move))}
      {sequence(message('PlayerStep', failed_step), message('ResultMoveOutcome', move), message('ResultInjuryRoll', injury))}
      {end}{board}</ReplayStep><EndGame><RulesEventGameFinished><MatchResult><GamerResults>
      <GamerResult><TeamResult><Score>2</Score></TeamResult></GamerResult>
      <GamerResult><TeamResult><Score>1</Score></TeamResult></GamerResult>
      </GamerResults></MatchResult></RulesEventGameFinished></EndGame></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()
    data = timeline.to_narrative_dict()

    assert data["format"] == "pybb3-narrative-timeline" and data["version"] == 1
    assert data["match"]["result"] == {
        "teams": [{"team_id": 0, "score": 2}, {"team_id": 1, "score": 1}],
        "score": [2, 1], "winner_team_id": 0,
    }
    moves = [event for event in data["events"] if event["type"] == "move"]
    assert len(moves) == 1
    assert moves[0]["half"] == 1 and moves[0]["team_turn"] == 1
    assert "messages" not in moves[0].get("details", {})
    assert "turns" not in data
    assert len({event["id"] for event in data["events"]}) == len(data["events"])
    saved = timeline.save_narrative(tmp_path / "narrative.json")
    assert json.loads(saved.read_text(encoding="utf-8"))["format"] == data["format"]


def test_narrative_result_treats_present_empty_score_as_zero():
    xml = b"""<Replay><Rosters/><EndGame><RulesEventGameFinished><MatchResult>
      <GamerResults><GamerResult><TeamResult><Score>2</Score></TeamResult></GamerResult>
      <GamerResult><TeamResult><Score/></TeamResult></GamerResult></GamerResults>
    </MatchResult></RulesEventGameFinished></EndGame></Replay>"""

    result = Replay.from_xml(xml).timeline().to_narrative_dict()["match"]["result"]

    assert result["score"] == [2, 0]
    assert result["winner_team_id"] == 0


def test_narrative_export_options_restore_moves_and_evidence():
    step = "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId><StepType>1</StepType></PlayerStep>"
    move = "<ResultMoveOutcome><Moved>1</Moved></ResultMoveOutcome>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultMoveOutcome', move))}</ReplayStep></Replay>".encode()

    event = Replay.from_xml(xml).timeline().to_narrative_dict(
        include_moves=True, include_evidence=True
    )["events"][0]

    assert event["type"] == "move"
    assert event["details"]["messages"][0]["type"] == "PlayerStep"


def test_narrative_checks_name_roll_purpose_and_preserve_team_reroll_chain():
    step = "<PlayerStep><PlayerId>40</PlayerId><TargetId>-1</TargetId><StepType>1</StepType></PlayerStep>"
    dodge = "<ResultRoll><Requirement>2</Requirement><Dice><Die><Value>4</Value></Die></Dice><RollType>2</RollType><Outcome>1</Outcome></ResultRoll>"
    first_rush = "<QuestionTeamRerollUsage><RollInfos><Requirement>2</Requirement><Dice><Die><Value>1</Value></Die></Dice><RollType>1</RollType><Outcome>0</Outcome></RollInfos></QuestionTeamRerollUsage>"
    reroll = "<ResultTeamRerollUsage><Used>1</Used></ResultTeamRerollUsage>"
    second_rush = "<ResultRoll><Requirement>2</Requirement><Dice><Die><Value>5</Value></Die></Dice><RollType>1</RollType><Outcome>1</Outcome></ResultRoll>"
    move = "<ResultMoveOutcome><Moved>1</Moved></ResultMoveOutcome>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultRoll', dodge), message('ResultMoveOutcome', move), message('QuestionTeamRerollUsage', first_rush), message('ResultTeamRerollUsage', reroll), message('ResultRoll', second_rush), message('ResultMoveOutcome', move))}</ReplayStep></Replay>".encode()

    event = Replay.from_xml(xml).timeline().to_narrative_dict()["events"][0]

    assert event["type"] == "move"
    assert event["checks"] == [
        {
            "type": "dodge", "subject": {"kind": "player", "id": 40},
            "required": 2, "attempts": [{"dice": [4], "outcome": "passed"}],
            "outcome": "passed",
        },
        {
            "type": "rush", "subject": {"kind": "player", "id": 40},
            "required": 2,
            "attempts": [
                {"dice": [1], "outcome": "failed"},
                {"dice": [5], "outcome": "passed", "reroll": "team"},
            ],
            "outcome": "passed", "reroll_offered": ["team"],
            "reroll_used": True,
        },
    ]
    assert "effects" not in event


def test_narrative_checks_merge_skill_reroll_into_same_check():
    step = "<PlayerStep><PlayerId>41</PlayerId><TargetId>-1</TargetId><StepType>1</StepType></PlayerStep>"
    failed = "<ResultRoll><Requirement>2</Requirement><Dice><Die><Value>1</Value></Die></Dice><RollType>2</RollType><Outcome>0</Outcome></ResultRoll>"
    dodge_skill = "<ResultSkillUsage><PlayerId>41</PlayerId><Skill>7</Skill><Used>1</Used></ResultSkillUsage>"
    passed = "<ResultRoll><Requirement>2</Requirement><Dice><Die><Value>3</Value></Die></Dice><RollType>2</RollType><Outcome>1</Outcome></ResultRoll>"
    move = "<ResultMoveOutcome><Moved>1</Moved></ResultMoveOutcome>"
    xml = f"<Replay><Rosters/><ReplayStep>{sequence(message('PlayerStep', step), message('ResultRoll', failed), message('ResultSkillUsage', dodge_skill), message('ResultRoll', passed), message('ResultMoveOutcome', move))}</ReplayStep></Replay>".encode()

    event = Replay.from_xml(xml).timeline().to_narrative_dict()["events"][0]

    assert event["checks"] == [{
        "type": "dodge", "subject": {"kind": "player", "id": 41},
        "required": 2,
        "attempts": [
            {"dice": [1], "outcome": "failed"},
            {"dice": [3], "outcome": "passed", "reroll": "dodge"},
        ],
        "outcome": "passed", "reroll_used": True,
    }]
