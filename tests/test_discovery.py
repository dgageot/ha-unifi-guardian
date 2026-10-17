import pytest

from custom_components.unifi_guardian.discovery import (
    ADDRESSING,
    DISCOVERY,
    SOAP,
    normalize_uuid,
    parse_response,
    probe,
)

UUID = "12345678-1234-4234-8234-123456789abc"
MESSAGE = "urn:uuid:request"


def response(uuid=UUID, message=MESSAGE):
    return f'''<s:Envelope xmlns:s="{SOAP}" xmlns:a="{ADDRESSING}"
    xmlns:d="{DISCOVERY}"><s:Header><a:RelatesTo>{message}</a:RelatesTo>
    <a:Action>{DISCOVERY}/ProbeMatches</a:Action></s:Header>
    <s:Body><d:ProbeMatches><d:ProbeMatch><a:EndpointReference>
    <a:Address>urn:uuid:{uuid}</a:Address></a:EndpointReference>
    <d:XAddrs>http://untrusted.example/never-fetch</d:XAddrs>
    </d:ProbeMatch></d:ProbeMatches></s:Body></s:Envelope>'''.encode()


def test_extracts_only_endpoint_uuid():
    assert parse_response(response(), MESSAGE) == {UUID}


def test_ignores_unrelated_response():
    assert not parse_response(response(message="wrong"), MESSAGE)


def test_invalid_uuid_is_ignored():
    assert not parse_response(response(uuid="not-a-uuid"), MESSAGE)


@pytest.mark.parametrize(
    "data",
    [
        b"garbage",
        b"x" * 40000,
        b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><x>&y;</x>',
    ],
)
def test_untrusted_xml_is_rejected(data):
    assert not parse_response(data, MESSAGE)


def test_uuid_normalization():
    assert normalize_uuid("URN:UUID:" + UUID.upper()) == UUID


@pytest.mark.parametrize("ip", ["not-an-ip", "127.0.0.1", "224.0.0.1", "0.0.0.0"])
async def test_nonclient_addresses_are_rejected(ip):
    assert not await probe(ip)
