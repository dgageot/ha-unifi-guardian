"""Thin adapter around the same UniFi library used by Home Assistant."""

import asyncio
from dataclasses import dataclass

from aiounifi.controller import Controller
from aiounifi.models.client import (
    AllClientListRequest,
    ClientBlockRequest,
    ClientListRequest,
)
from aiounifi.models.configuration import Configuration
from aiounifi.models.site import SiteListRequest


@dataclass(frozen=True)
class Client:
    mac: str
    ip: str = ""
    name: str = ""
    wired: bool = False
    blocked: bool = False


def clients_from_response(response: dict) -> dict[str, Client]:
    return {
        row["mac"].lower(): Client(
            mac=row["mac"].lower(),
            ip=row.get("ip", ""),
            name=row.get("name") or row.get("hostname") or row["mac"],
            wired=row.get("is_wired", False),
            blocked=row.get("blocked", False),
        )
        for row in response.get("data", [])
        if row.get("mac")
    }


class UnifiAPI:
    def __init__(self, session, data: dict, ssl_context):
        self.controller = Controller(
            Configuration(
                session=session,
                host=data["host"],
                port=data["port"],
                username=data["username"],
                password=data["password"],
                site=data.get("site", "default"),
                ssl_context=ssl_context,
            )
        )

    async def login(self):
        async with asyncio.timeout(20):
            await self.controller.login()

    async def sites(self):
        async with asyncio.timeout(20):
            result = await self.controller.request(SiteListRequest.create())
        return result.get("data", [])

    async def active(self) -> dict[str, Client]:
        async with asyncio.timeout(20):
            result = await self.controller.request(ClientListRequest.create())
        return clients_from_response(result)

    async def records(self) -> dict[str, Client]:
        async with asyncio.timeout(20):
            result = await self.controller.request(AllClientListRequest.create())
        return clients_from_response(result)

    async def set_blocked(self, mac: str, blocked: bool):
        async with asyncio.timeout(20):
            await self.controller.request(ClientBlockRequest.create(mac, blocked))
