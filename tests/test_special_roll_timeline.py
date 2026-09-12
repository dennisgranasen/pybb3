import base64

from bb3.replay import Replay


def b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def message(name: str, xml: str) -> str:
    return (
        f"<StringMessage><Name>{b64(name)}</Name>"
        f"<MessageData>{b64(b64(xml))}</MessageData></StringMessage>"
    )


def sequence(*messages: str) -> str:
    return (
        "<EventExecuteSequence><Sequence><StepResult><Results>"
        + "".join(messages)
        + "</Results></StepResult></Sequence></EventExecuteSequence>"
    )


def test_ball_and_chain_direction_is_a_semantic_direction_roll():
    step = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId>"
        "<StepType>31</StepType></PlayerStep>"
    )
    direction = (
        "<ResultRoll><Requirement>0</Requirement><Difficulty>0</Difficulty>"
        "<Dice><Die><Value>4</Value></Die></Dice><RollType>87</RollType>"
        "<Outcome>2</Outcome></ResultRoll>"
    )
    moved = "<ResultMoveOutcome><Moved>1</Moved></ResultMoveOutcome>"
    xml = f"""<Replay><Rosters/><ReplayStep>{sequence(
        message("PlayerStep", step),
        message("ResultRoll", direction),
        message("ResultMoveOutcome", moved),
    )}</ReplayStep></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    event = timeline.events[0]
    effect = next(x for x in event.effects if x.type == "ball_and_chain_direction")
    assert effect.subject.id == 1
    assert effect.outcome == 4

    narrative = timeline.to_narrative_dict(include_moves=True)
    check = next(
        x for x in narrative["events"][0]["checks"]
        if x["type"] == "ball_and_chain_direction"
    )
    assert check["outcome"] == 4
    assert check["attempts"][0]["dice"] == [4]
    assert check["attempts"][0]["outcome"] == 4


def test_ball_and_chain_direction_is_kept_when_move_becomes_a_block():
    direction_step = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>2</TargetId>"
        "<StepType>31</StepType></PlayerStep>"
    )
    direction = (
        "<ResultRoll><Requirement>0</Requirement><Difficulty>0</Difficulty>"
        "<Dice><Die><Value>3</Value></Die></Dice><RollType>87</RollType>"
        "<Outcome>2</Outcome></ResultRoll>"
    )
    block_step = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>2</TargetId>"
        "<StepType>6</StepType></PlayerStep>"
    )
    block = (
        "<ResultBlockOutcome><AttackerId>1</AttackerId><DefenderId>2</DefenderId>"
        "<Outcome>1</Outcome></ResultBlockOutcome>"
    )
    xml = f"""<Replay><Rosters/><ReplayStep>{sequence(
        message("PlayerStep", direction_step),
        message("ResultRoll", direction),
        message("PlayerStep", block_step),
        message("ResultBlockOutcome", block),
    )}</ReplayStep></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    event = timeline.events[0]
    assert event.type == "block"
    effect = next(x for x in event.effects if x.type == "ball_and_chain_direction")
    assert effect.subject.id == 1
    assert effect.outcome == 3


def test_bomb_explosion_hit_is_attached_to_the_affected_player():
    throw = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId>"
        "<StepType>32</StepType></PlayerStep>"
    )
    explosion = "<ResultBombExplosion><Cell><X>1</X><Y>1</Y></Cell></ResultBombExplosion>"
    target = (
        "<PlayerStep><PlayerId>2</PlayerId><TargetId>-1</TargetId>"
        "<StepType>33</StepType></PlayerStep>"
    )
    hit = (
        "<ResultRoll><Requirement>4</Requirement><Difficulty>4</Difficulty>"
        "<Dice><Die><Value>6</Value></Die></Dice><RollType>88</RollType>"
        "<Outcome>1</Outcome></ResultRoll>"
    )
    xml = f"""<Replay><Rosters/><ReplayStep>{sequence(
        message("PlayerStep", throw),
        message("ResultBombExplosion", explosion),
        message("PlayerStep", target),
        message("ResultRoll", hit),
    )}</ReplayStep></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    event = timeline.events[0]
    assert event.type == "bomb_explosion"
    assert event.actor.id == 1
    effect = next(x for x in event.effects if x.type == "bomb_explosion_hit")
    assert effect.subject.id == 2
    assert effect.outcome is True

    narrative = timeline.to_narrative_dict(include_moves=True)
    check = next(
        x for x in narrative["events"][0]["checks"]
        if x["type"] == "bomb_explosion_hit"
    )
    assert check["subject"]["id"] == 2
    assert check["outcome"] == "passed"


def test_bloodlust_is_not_duplicated_as_an_action_effect():
    activation = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId>"
        "<StepType>0</StepType></PlayerStep>"
    )
    bloodlust = (
        "<ResultRoll><Requirement>2</Requirement><Difficulty>2</Difficulty>"
        "<Dice><Die><Value>5</Value></Die></Dice><RollType>96</RollType>"
        "<Outcome>1</Outcome></ResultRoll>"
    )
    move = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId>"
        "<StepType>1</StepType></PlayerStep>"
    )
    moved = "<ResultMoveOutcome><Moved>1</Moved></ResultMoveOutcome>"
    xml = f"""<Replay><Rosters/><ReplayStep>{sequence(
        message("PlayerStep", activation),
        message("ResultRoll", bloodlust),
        message("PlayerStep", move),
        message("ResultMoveOutcome", moved),
    )}</ReplayStep></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    check = next(x for x in timeline.events if x.type == "negatrait_check")
    action = next(x for x in timeline.events if x.type == "move")
    assert check.details["trait"] == "bloodlust"
    assert all(effect.type != "bloodlust" for effect in action.effects)
