"""Home Assistant lifecycle and persisted requested state."""

import logging
from datetime import timedelta

from aiohttp import ClientError
from aiounifi.errors import AiounifiException, LoginRequired, Unauthorized
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, POLL_SECONDS
from .engine import Engine, State

LOGGER = logging.getLogger(__name__)


class GuardianCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api):
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=POLL_SECONDS),
        )
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.engine = Engine(api, entry.data["uuid"], State(), self.store.async_save)

    async def load(self):
        data = await self.store.async_load()
        self.engine.state = (
            State(**data)
            if data is not None
            else State(known=[self.entry.data["initial_mac"]])
        )
        if data is None:
            await self.engine.persist()

    async def _async_update_data(self):
        try:
            await self.engine.update()
        except (Unauthorized, LoginRequired) as err:
            raise ConfigEntryAuthFailed("UniFi login expired or was rejected") from err
        except (AiounifiException, ClientError, TimeoutError, OSError) as err:
            raise UpdateFailed("Unable to reconcile UniFi client blocking") from err
        return self.engine.status

    async def set_requested(self, blocked):
        try:
            await self.engine.request(blocked)
        except (AiounifiException, ClientError, TimeoutError, OSError) as err:
            self.async_set_update_error(UpdateFailed("UniFi command not confirmed"))
            raise HomeAssistantError(
                "Could not confirm the request. Check the switch's requested state "
                "and Enforcement status. Persisted requests will be retried."
            ) from err
        self.async_set_updated_data(self.engine.status)
