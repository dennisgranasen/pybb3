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


def test_bloodlust_failure_and_bite_are_linked():
    roster = (
        "<TeamRoster><Players>"
        f"<PlayerData><Name>{b64('Vampire')}</Name><Id>1</Id></PlayerData>"
        f"<PlayerData><Name>{b64('Thrall')}</Name><Id>2</Id></PlayerData>"
        "</Players>"
        f"<Name>{b64('Vampires')}</Name><Team><TeamId>0</TeamId></Team>"
        "</TeamRoster>"
    )
    activation = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId>"
        "<StepType>0</StepType></PlayerStep>"
    )
    failed = (
        "<ResultRoll><Requirement>2</Requirement><Difficulty>2</Difficulty>"
        "<Dice><Die><Value>1</Value></Die></Dice><RollType>96</RollType>"
        "<Outcome>0</Outcome></ResultRoll>"
    )
    changed = "<ResultSequenceChanged><OldSequence>1</OldSequence><NewSequence>1</NewSequence></ResultSequenceChanged>"
    pending = (
        "<ResultAddPlayerEffect><PlayerId>1</PlayerId><Effect>"
        "<ProviderType>4</ProviderType><ProviderId>103</ProviderId>"
        "<EffectId>64</EffectId></Effect></ResultAddPlayerEffect>"
    )
    bite_step = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId>"
        "<StepType>34</StepType></PlayerStep>"
    )
    bite = "<ResultBite><VictimId>2</VictimId></ResultBite>"
    injury = "<ResultInjuryRoll><Outcome>0</Outcome></ResultInjuryRoll>"

    xml = f"""<Replay><Rosters>{roster}</Rosters>
      <ReplayStep>{sequence(
          message('PlayerStep', activation),
          message('ResultRoll', failed),
          message('ResultSequenceChanged', changed),
          message('ResultAddPlayerEffect', pending),
      )}</ReplayStep>
      <ReplayStep>{sequence(
          message('PlayerStep', bite_step),
          message('ResultBite', bite),
          message('ResultInjuryRoll', injury),
      )}</ReplayStep>
    </Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    assert [event.type for event in timeline.events] == [
        "negatrait_check", "bloodlust_bite",
    ]
    check, bite_event = timeline.events
    assert check.actor.id == 1
    assert check.details["trait"] == "bloodlust"
    assert check.outcome == "failed"
    assert bite_event.actor.id == 1
    assert bite_event.target.id == 2
    assert bite_event.outcome == "teammate_bitten"
    assert bite_event.caused_by == check.id
    assert bite_event.effects[0].type == "injury"
    assert bite_event.effects[0].subject.id == 2
    assert not timeline.unresolved


def test_bloodlust_no_victim_records_lost_tackle_zone():
    activation = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId>"
        "<StepType>0</StepType></PlayerStep>"
    )
    failed = (
        "<ResultRoll><Requirement>2</Requirement><Difficulty>2</Difficulty>"
        "<Dice><Die><Value>1</Value></Die></Dice><RollType>96</RollType>"
        "<Outcome>0</Outcome></ResultRoll>"
    )
    bite_step = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>-1</TargetId>"
        "<StepType>34</StepType></PlayerStep>"
    )
    bite = "<ResultBite><VictimId>-1</VictimId></ResultBite>"
    end_effect = (
        "<ResultEndPlayerEffect><PlayerId>1</PlayerId><Effect>"
        "<ProviderType>4</ProviderType><ProviderId>103</ProviderId>"
        "<EffectId>64</EffectId></Effect></ResultEndPlayerEffect>"
    )
    no_zone = (
        "<ResultAddPlayerEffect><PlayerId>1</PlayerId><Effect>"
        "<ProviderType>4</ProviderType><ProviderId>103</ProviderId>"
        "<EffectId>44</EffectId></Effect></ResultAddPlayerEffect>"
    )

    xml = f"""<Replay><Rosters/>
      <ReplayStep>{sequence(
          message('PlayerStep', activation), message('ResultRoll', failed)
      )}</ReplayStep>
      <ReplayStep>{sequence(
          message('PlayerStep', bite_step),
          message('ResultEndPlayerEffect', end_effect),
          message('ResultBite', bite),
          message('ResultAddPlayerEffect', no_zone),
      )}</ReplayStep>
    </Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    check, bite_event = timeline.events
    assert check.type == "negatrait_check"
    assert check.details["trait"] == "bloodlust"
    assert bite_event.type == "bloodlust_bite"
    assert bite_event.outcome == "no_victim"
    assert bite_event.caused_by == check.id
    assert bite_event.effects[0].type == "lost_tackle_zone"
    assert bite_event.effects[0].subject.id == 1
    assert not timeline.unresolved


def test_hypnotic_gaze_has_actor_target_and_outcome():
    gaze_step = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>2</TargetId>"
        "<StepType>23</StepType></PlayerStep>"
    )
    gaze_roll = (
        "<ResultRoll><Requirement>2</Requirement><Difficulty>2</Difficulty>"
        "<Dice><Die><Value>4</Value></Die></Dice><RollType>66</RollType>"
        "<Outcome>1</Outcome></ResultRoll>"
    )
    gaze_effect = (
        "<ResultAddPlayerEffect><PlayerId>2</PlayerId><Effect>"
        "<ProviderType>4</ProviderType><ProviderId>78</ProviderId>"
        "<EffectId>44</EffectId></Effect></ResultAddPlayerEffect>"
    )

    xml = f"""<Replay><Rosters/><ReplayStep>{sequence(
        message('PlayerStep', gaze_step),
        message('ResultRoll', gaze_roll),
        message('ResultAddPlayerEffect', gaze_effect),
    )}</ReplayStep></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    assert len(timeline.events) == 1
    event = timeline.events[0]
    assert event.type == "hypnotic_gaze"
    assert event.actor.id == 1
    assert event.target.id == 2
    assert event.outcome == "passed"
    assert not timeline.unresolved


def test_bloodlust_check_uses_activation_actor_before_later_catch():
    activation = (
        "<PlayerStep><PlayerId>1</PlayerId><TargetId>2</TargetId>"
        "<StepType>0</StepType></PlayerStep>"
    )
    bloodlust = (
        "<ResultRoll><Requirement>2</Requirement><Difficulty>2</Difficulty>"
        "<Dice><Die><Value>5</Value></Die></Dice><RollType>96</RollType>"
        "<Outcome>1</Outcome></ResultRoll>"
    )
    catch_step = (
        "<PlayerStep><PlayerId>2</PlayerId><TargetId>-1</TargetId>"
        "<StepType>4</StepType></PlayerStep>"
    )
    catch_roll = (
        "<ResultRoll><Requirement>3</Requirement><Difficulty>3</Difficulty>"
        "<Dice><Die><Value>6</Value></Die></Dice><RollType>7</RollType>"
        "<Outcome>1</Outcome></ResultRoll>"
    )

    xml = f"""<Replay><Rosters/><ReplayStep>{sequence(
        message('PlayerStep', activation),
        message('ResultRoll', bloodlust),
        message('PlayerStep', catch_step),
        message('ResultRoll', catch_roll),
    )}</ReplayStep></Replay>""".encode()

    timeline = Replay.from_xml(xml).timeline()

    check = next(event for event in timeline.events if event.type == "negatrait_check")
    assert check.details["trait"] == "bloodlust"
    assert check.actor.id == 1
