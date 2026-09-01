from __future__ import annotations

import struct

import pytest

from bb3.protocol import BB3ProtocolError, recv_exact, recv_frame, send_frame


class FragmentedSocket:
    def __init__(self, data: bytes, fragment_size: int = 3):
        self.data = bytearray(data)
        self.fragment_size = fragment_size

    def recv(self, size: int) -> bytes:
        count = min(size, self.fragment_size, len(self.data))
        result = bytes(self.data[:count])
        del self.data[:count]
        return result


def encoded_frame(body: str, **overrides: str) -> bytes:
    attributes = {
        "type": "textxml",
        "size": str(len(body.encode("utf-8"))),
        "zipped": "false",
        "MessageName": "ResponseExample",
        "MessageToken": "12",
        "sizeBeforeCompression": str(len(body.encode("utf-8"))),
    }
    attributes.update(overrides)
    attrs = " ".join(f'{key}="{value}"' for key, value in attributes.items())
    header = f"<Header><Data {attrs}/></Header>".encode()
    return struct.pack("<I", len(header)) + header + body.encode()


def test_recv_exact_handles_fragmented_reads():
    assert recv_exact(FragmentedSocket(b"abcdef", 2), 6) == b"abcdef"


def test_recv_exact_rejects_truncated_and_negative_reads():
    with pytest.raises(ConnectionError):
        recv_exact(FragmentedSocket(b"abc"), 4)
    with pytest.raises(ValueError):
        recv_exact(FragmentedSocket(b""), -1)


def test_recv_frame_handles_fragmented_frame():
    body = "<ResponseExample><Result>1</Result></ResponseExample>"
    frame = recv_frame(FragmentedSocket(encoded_frame(body), 2))
    assert frame.message_name == "ResponseExample"
    assert frame.message_token == 12
    assert frame.body == body


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"size": "invalid"}, "invalid size"),
        ({"size": "-1"}, "body length"),
        ({"MessageToken": "invalid"}, "MessageToken"),
        ({"zipped": "true"}, "compression"),
    ],
)
def test_recv_frame_rejects_unsupported_headers(overrides, message):
    with pytest.raises(BB3ProtocolError, match=message):
        recv_frame(FragmentedSocket(encoded_frame("<x/>", **overrides)))


def test_send_frame_round_trip():
    class RecordingSocket:
        data = b""

        def sendall(self, data):
            self.data += data

    sock = RecordingSocket()
    send_frame(sock, "ResponseExample", 4, "<ResponseExample/>")
    frame = recv_frame(FragmentedSocket(sock.data))
    assert frame.message_name == "ResponseExample"
    assert frame.message_token == 4
    assert frame.body == "<ResponseExample/>"
