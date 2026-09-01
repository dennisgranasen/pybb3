from bb3.security import REDACTED, redact_bytes, redact_mapping, redact_text


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


def test_redact_bytes_preserves_capture_offsets_and_lengths():
    source = (
        b"\x04\x00\x00\x00junk<AuthToken>ticket</AuthToken>"
        b'\n{"refreshToken":"refresh"}\nSTEAM_PASSWORD=password'
    )

    result = redact_bytes(source)

    assert len(result) == len(source)
    assert b"ticket" not in result
    assert b':"refresh"' not in result
    assert b"=password" not in result
    assert b"<AuthToken>******</AuthToken>" in result
