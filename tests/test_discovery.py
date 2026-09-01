from unittest.mock import patch

from bb3_client.discovery import discover_bb3_endpoint


class FakeResponse:
    status = 200
    reason = "OK"

    def read(self):
        return b"tcp://app18.bb3.cyanide-studio.com:17010"


class FakeConnection:
    def __init__(self, *args, **kwargs):
        self.request_args = None

    def request(self, *args, **kwargs):
        self.request_args = (args, kwargs)

    def getresponse(self):
        return FakeResponse()

    def close(self):
        pass


def test_discovery_parses_tcp_endpoint():
    with patch("bb3_client.discovery.http.client.HTTPConnection", FakeConnection):
        endpoint = discover_bb3_endpoint("bb3-win-steam-shipping-57968")
    assert endpoint.host == "app18.bb3.cyanide-studio.com"
    assert endpoint.port == 17010
