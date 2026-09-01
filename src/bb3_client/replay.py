import base64
import zlib


def decode_replay_data(replay_data: str) -> bytes:
    layer1 = base64.b64decode(replay_data)
    layer2 = base64.b64decode(layer1)
    xml = zlib.decompress(layer2)
    if not xml.lstrip().startswith(b"<Replay"):
        raise ValueError("Decoded ReplayData is not Replay XML")
    return xml
