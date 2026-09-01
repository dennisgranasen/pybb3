import base64
import zlib

from bb3.replay import decode_replay_data


def test_replay_decode_chain():
    xml = b"<Replay><ReplayVersion>1-4-0-0</ReplayVersion></Replay>"
    encoded = base64.b64encode(base64.b64encode(zlib.compress(xml))).decode()
    assert decode_replay_data(encoded) == xml
