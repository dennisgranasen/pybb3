from bb3.security import REDACTED, redact_mapping, redact_text


def test_redact_text_handles_protocol_and_config_formats():
    source = (
        "<RequestLogin><AuthToken>ticket-value</AuthToken></RequestLogin>\n"
        '"refreshToken": "refresh-value"\n'
        "STEAM_PASSWORD=password-value\n"
        "Authorization: Bearer bearer-value"
    )

    result = redact_text(source)

    assert "ticket-value" not in result
    assert "refresh-value" not in result
    assert "password-value" not in result
    assert "bearer-value" not in result
    assert result.count(REDACTED) == 4


def test_redact_mapping_is_recursive_and_does_not_mutate_input():
    source = {
        "username": "coach",
        "refreshToken": "secret",
        "nested": {
            "password": "secret-2",
            "safe": "value",
            "messages": ["AuthToken=secret-3"],
        },
    }

    result = redact_mapping(source)

    assert result == {
        "username": "coach",
        "refreshToken": REDACTED,
        "nested": {
            "password": REDACTED,
            "safe": "value",
            "messages": [f"AuthToken={REDACTED}"],
        },
    }
    assert source["refreshToken"] == "secret"
