from bb3_client.encoding import b64_decode_text, b64_encode_text


def test_text_roundtrip():
    value = "I got woodzies"
    assert b64_decode_text(b64_encode_text(value)) == value
