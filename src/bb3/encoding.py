import base64
import json
from typing import Any


def b64_encode_text(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def b64_decode_text(value: str) -> str:
    return base64.b64decode(value).decode("utf-8")


def b64_encode_json(value: Any, *, pretty: bool = False) -> str:
    if pretty:
        text = json.dumps(value, indent=2)
    else:
        text = json.dumps(value, separators=(",", ":"))
    return b64_encode_text(text)


def b64_decode_json(value: str) -> Any:
    return json.loads(b64_decode_text(value))
