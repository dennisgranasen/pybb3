from __future__ import annotations

import pytest

from bb3 import BB3Data, BB3DataError


def make_installation(root):
    offline = root / "BB3" / "Content" / "OfflineServer"
    offline.mkdir(parents=True)
    rules = offline / "bb3rulesengine.zip"
    data = offline / "bb3.zip"
    rules.write_bytes(b"rules")
    data.write_bytes(b"data")
    return rules.resolve(), data.resolve()


def test_from_env_uses_dotenv_installation(tmp_path):
    installation = tmp_path / "Blood Bowl 3"
    rules, data = make_installation(installation)
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"BB3_PATH={installation}\n", encoding="utf-8")

    resolved = BB3Data.from_env(environ={}, dotenv_path=dotenv)

    assert resolved == BB3Data(rules, data)


def test_environment_overrides_dotenv(tmp_path):
    dotenv_installation = tmp_path / "dotenv"
    environment_installation = tmp_path / "environment"
    make_installation(dotenv_installation)
    rules, data = make_installation(environment_installation)
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"BB3_PATH={dotenv_installation}\n", encoding="utf-8")

    resolved = BB3Data.from_env(
        environ={"BB3_PATH": str(environment_installation)},
        dotenv_path=dotenv,
    )

    assert resolved == BB3Data(rules, data)


def test_individual_override_takes_precedence_over_installation(tmp_path):
    installation = tmp_path / "installation"
    _, data = make_installation(installation)
    override = tmp_path / "custom-rules.zip"
    override.write_bytes(b"rules")

    resolved = BB3Data.from_env(
        environ={
            "BB3_PATH": str(installation),
            "BB3_RULES_ENGINE_ZIP": str(override),
        },
        dotenv_path=tmp_path / ".env",
    )

    assert resolved == BB3Data(override.resolve(), data)


def test_two_overrides_do_not_require_installation_path(tmp_path):
    rules = tmp_path / "rules.zip"
    data = tmp_path / "data.zip"
    rules.write_bytes(b"rules")
    data.write_bytes(b"data")

    resolved = BB3Data.from_env(
        environ={
            "BB3_RULES_ENGINE_ZIP": str(rules),
            "BB3_DATA_ZIP": str(data),
        },
        dotenv_path=tmp_path / ".env",
    )

    assert resolved == BB3Data(rules.resolve(), data.resolve())


def test_missing_files_error_lists_attempted_locations(tmp_path):
    installation = tmp_path / "missing-installation"

    with pytest.raises(BB3DataError) as exc_info:
        BB3Data.from_installation(installation)

    message = str(exc_info.value)
    assert str(installation.resolve()) in message
    assert "bb3rulesengine.zip" in message
    assert "bb3.zip" in message
