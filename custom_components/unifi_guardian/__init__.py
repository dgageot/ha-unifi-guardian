"""UniFi Guardian: discovery-based client block control."""

from aiohttp import ClientError
from aiounifi.errors import AiounifiException, LoginRequired, Unauthorized
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .connection import make_connection
from .const import PLATFORMS
from .coordinator import GuardianCoordinator


async def async_setup_entry(hass, entry):
    session, api = await make_connection(hass, entry.data)
    try:
        await api.login()
        coordinator = GuardianCoordinator(hass, entry, api)
        await coordinator.load()
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = (coordinator, session)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except (Unauthorized, LoginRequired) as err:
        await session.close()
        raise ConfigEntryAuthFailed("UniFi authentication failed") from err
    except (AiounifiException, ClientError, TimeoutError, OSError) as err:
        await session.close()
        raise ConfigEntryNotReady("Cannot connect to UniFi") from err
    except BaseException:
        await session.close()
        raise
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator, session = entry.runtime_data
        await coordinator.async_shutdown()
        await session.close()
        return True
    return False
