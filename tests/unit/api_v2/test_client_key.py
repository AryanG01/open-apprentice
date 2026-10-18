from types import SimpleNamespace

from open_apprentice.api.v2.routes import client_key


def _req(xff=None, host="10.0.0.1"):
    h = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(headers=h, client=SimpleNamespace(host=host))


def test_rightmost_forwarded_entry_is_the_client_so_spoofing_prefixes_changes_nothing():
    assert client_key(_req("6.6.6.6, 1.2.3.4")) == "1.2.3.4"
    assert client_key(_req("9.9.9.9, 6.6.6.6, 1.2.3.4")) == "1.2.3.4"


def test_without_the_header_the_socket_address_is_used():
    assert client_key(_req()) == "10.0.0.1"
    assert client_key(SimpleNamespace(headers={}, client=None)) == "?"
