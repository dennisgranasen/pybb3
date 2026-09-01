from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

import pytest

from bb3.client import BB3Client, BB3RequestError
from bb3.protocol import BB3Frame


def frame(body: str, name: str = "ResponseExample") -> BB3Frame:
    return BB3Frame(message_name=name, message_token=7, body=body)


def test_success_without_result_returns_xml_root():
    response = frame("<ResponseCreateTeam><Exceptions/><IdTeam>abc</IdTeam></ResponseCreateTeam>")

    root = BB3Client._assert_success(response)

    assert isinstance(root, ET.Element)
    assert root.findtext("IdTeam") == "abc"


def test_direct_exception_exposes_structured_data():
    description = base64.b64encode(b"Already logged in").decode("ascii")
    response = frame(
        f"<ResponseLogin><Exception><Code>11</Code><Desc>{description}</Desc></Exception></ResponseLogin>",
        "ResponseLogin",
    )

    with pytest.raises(BB3RequestError) as exc_info:
        BB3Client._assert_success(response)

    error = exc_info.value
    assert error.code == 11
    assert error.description == "Already logged in"
    assert error.message_name == "ResponseLogin"
    assert error.raw_response == response.body
    assert error.frame is response


def test_wrapped_exception_is_supported():
    response = frame(
        "<ResponseExample><Exceptions><Exception><Code>42</Code><Desc>not-base64!</Desc>"
        "</Exception></Exceptions></ResponseExample>"
    )

    with pytest.raises(BB3RequestError) as exc_info:
        BB3Client._assert_success(response)

    assert exc_info.value.code == 42
    assert exc_info.value.description == "not-base64!"


def test_result_zero_is_a_structured_error():
    response = frame(
        "<ResponseLogin><Result>0</Result><AuthToken>secret</AuthToken></ResponseLogin>",
        "ResponseLogin",
    )

    with pytest.raises(BB3RequestError) as exc_info:
        BB3Client._assert_success(response)

    assert exc_info.value.description == "Result=0"
    assert exc_info.value.message_name == "ResponseLogin"
    assert exc_info.value.raw_response == response.body
    assert "secret" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_request_returns_xml_and_request_frame_preserves_raw_frame(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    response = frame("<ResponseExample><Result>1</Result><Value>ok</Value></ResponseExample>")
    monkeypatch.setattr(client, "request_frame", lambda *args, **kwargs: response)

    root = client.request("RequestExample", "ResponseExample")

    assert root.findtext("Value") == "ok"
