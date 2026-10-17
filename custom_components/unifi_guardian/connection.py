"""Isolated sessions: never share UniFi authentication cookies."""

import ssl
from contextlib import asynccontextmanager

from aiohttp import ClientSession, ClientTimeout, CookieJar

from .api import UnifiAPI


async def make_connection(hass, data):
    context = (
        await hass.async_add_executor_job(ssl.create_default_context)
        if data.get("verify_ssl", True)
        else False
    )
    session = ClientSession(
        cookie_jar=CookieJar(unsafe=True), timeout=ClientTimeout(total=20)
    )
    return session, UnifiAPI(session, data, context)


@asynccontextmanager
async def connection(hass, data):
    session, api = await make_connection(hass, data)
    try:
        await api.login()
        yield api
    finally:
        await session.close()
