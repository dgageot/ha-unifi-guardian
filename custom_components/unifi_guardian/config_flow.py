"""UI-only enrollment, credential updates and reauthentication."""

from ipaddress import ip_address

import voluptuous as vol
from aiohttp import ClientError
from aiounifi.errors import (
    AiounifiException,
    Forbidden,
    LoginRequired,
    NoPermission,
    TwoFaTokenRequired,
    Unauthorized,
)
from homeassistant import config_entries
from homeassistant.helpers import selector

from .connection import connection
from .const import DOMAIN
from .discovery import probe

AUTH_ERRORS = (Unauthorized, LoginRequired, Forbidden, NoPermission, TwoFaTokenRequired)
CONNECT_ERRORS = (AiounifiException, ClientError, TimeoutError, OSError)


def host(value):
    value = str(value).strip().lower()
    if not value or any(c in value for c in "/:@?# "):
        raise vol.Invalid("Enter a hostname or IPv4 address without scheme or port")
    return value


class GuardianConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._data = {}
        self._sites = {}
        self._clients = {}
        self._uuids = []
        self._selected = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            try:
                async with connection(self.hass, self._data) as api:
                    sites = await api.sites()
                self._sites = {
                    row["name"]: row.get("desc", row["name"])
                    for row in sites
                    if row.get("role") in ("admin", "super_admin")
                }
                if not self._sites:
                    errors["base"] = "no_permission"
                elif self.source in ("reauth", "reconfigure"):
                    entry = (
                        self._get_reauth_entry()
                        if self.source == "reauth"
                        else self._get_reconfigure_entry()
                    )
                    if entry.data["site"] not in self._sites:
                        errors["base"] = "no_permission"
                    else:
                        return self.async_update_reload_and_abort(
                            entry, data_updates=user_input
                        )
                else:
                    return await self.async_step_site()
            except AUTH_ERRORS:
                errors["base"] = "invalid_auth"
            except CONNECT_ERRORS:
                errors["base"] = "cannot_connect"
        schema = vol.Schema(
            {
                vol.Required("host", default=self._data.get("host", "")): host,
                vol.Required("port", default=self._data.get("port", 443)): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Required("username", default=self._data.get("username", "")): str,
                vol.Required("password"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    "verify_ssl", default=self._data.get("verify_ssl", True)
                ): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_site(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._data["site"] = user_input["site"]
            try:
                async with connection(self.hass, self._data) as api:
                    active = await api.active()
                self._clients = {
                    mac: client
                    for mac, client in active.items()
                    if client.ip and not client.wired and not client.blocked
                }
                if self._clients:
                    return await self.async_step_target()
                errors["base"] = "no_clients"
            except AUTH_ERRORS:
                errors["base"] = "invalid_auth"
            except CONNECT_ERRORS:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="site",
            errors=errors,
            data_schema=vol.Schema({vol.Required("site"): vol.In(self._sites)}),
        )

    async def async_step_target(self, user_input=None):
        errors = {}
        if user_input is not None:
            selected = self._clients[user_input["client"]]
            try:
                # Avoid enrolling a stale DHCP mapping.
                async with connection(self.hass, self._data) as api:
                    active = await api.active()
                    current = active.get(selected.mac)
                    if not current or current.ip != selected.ip or current.wired:
                        return self.async_abort(reason="client_changed")
                    ip_address(current.ip)
                    self._uuids = sorted(await probe(current.ip))
                    fresh = await api.active()
                    if (
                        fresh.get(current.mac) != current
                        or sum(c.ip == current.ip for c in fresh.values()) != 1
                    ):
                        return self.async_abort(reason="client_changed")
                if self._uuids:
                    self._selected = current
                    return await self.async_step_confirm()
                errors["base"] = "discovery_failed"
            except AUTH_ERRORS:
                errors["base"] = "invalid_auth"
            except (*CONNECT_ERRORS, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="target",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("client"): vol.In(
                        {
                            mac: f"{c.name} ({c.ip}, {mac})"
                            for mac, c in self._clients.items()
                        }
                    )
                }
            ),
        )

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            uuid = user_input["uuid"]
            await self.async_set_unique_id(
                f"{self._data['host']}:{self._data['port']}/{self._data['site']}/{uuid}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input["name"],
                data={
                    **self._data,
                    "uuid": uuid,
                    "name": user_input["name"],
                    "initial_mac": self._selected.mac,
                },
            )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=self._selected.name): str,
                    vol.Required("uuid", default=self._uuids[0]): vol.In(self._uuids),
                }
            ),
        )

    async def async_step_reauth(self, entry_data):
        self._data = dict(entry_data)
        return await self.async_step_user()

    async def async_step_reconfigure(self, user_input=None):
        self._data = dict(self._get_reconfigure_entry().data)
        return await self.async_step_user()
