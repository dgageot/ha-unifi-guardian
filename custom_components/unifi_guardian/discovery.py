"""Bounded, unicast WS-Discovery probes; no advertised URLs are followed."""

import asyncio
import socket
from ipaddress import IPv4Address
from uuid import UUID, uuid4
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

SOAP = "http://www.w3.org/2003/05/soap-envelope"
ADDRESSING = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
DISCOVERY = "http://schemas.xmlsoap.org/ws/2005/04/discovery"
NS = {"s": SOAP, "a": ADDRESSING, "d": DISCOVERY}


def normalize_uuid(value: str) -> str:
    return str(UUID(value.lower().removeprefix("urn:uuid:")))


def parse_response(data: bytes, message_id: str) -> set[str]:
    if len(data) > 32768:
        return set()
    try:
        root = fromstring(data)
        if root.findtext("s:Header/a:RelatesTo", namespaces=NS) != message_id:
            return set()
        if (
            root.findtext("s:Header/a:Action", namespaces=NS)
            != f"{DISCOVERY}/ProbeMatches"
        ):
            return set()
        result = set()
        for element in root.findall(
            "s:Body/d:ProbeMatches/d:ProbeMatch/a:EndpointReference/a:Address", NS
        ):
            try:
                result.add(normalize_uuid(element.text or ""))
            except ValueError:
                continue
        return result
    except ParseError, DefusedXmlException:
        return set()


async def probe(ip: str) -> set[str]:
    try:
        address = IPv4Address(ip)
    except ValueError:
        return set()
    if address.is_multicast or address.is_unspecified or address.is_loopback:
        return set()
    message_id = f"urn:uuid:{uuid4()}"
    packet = (
        f'<s:Envelope xmlns:s="{SOAP}" xmlns:a="{ADDRESSING}" xmlns:d="{DISCOVERY}">'
        f"<s:Header><a:Action>{DISCOVERY}/Probe</a:Action>"
        f"<a:MessageID>{message_id}</a:MessageID>"
        f"<a:ReplyTo><a:Address>{ADDRESSING}/role/anonymous</a:Address></a:ReplyTo>"
        "<a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>"
        "</s:Header><s:Body><d:Probe/></s:Body></s:Envelope>"
    ).encode()
    loop = asyncio.get_running_loop()
    result: set[str] = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        try:
            async with asyncio.timeout(2.0):
                await loop.sock_connect(sock, (str(address), 3702))
                await loop.sock_sendall(sock, packet)
                while True:
                    data = await loop.sock_recv(sock, 65535)
                    result.update(parse_response(data, message_id))
        except TimeoutError, OSError:
            pass
    return result
