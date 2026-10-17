from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiounifi.errors import Unauthorized
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.unifi_guardian.api import Client
from custom_components.unifi_guardian.config_flow import GuardianConfigFlow
from custom_components.unifi_guardian.coordinator import GuardianCoordinator
from custom_components.unifi_guardian.engine import State
from custom_components.unifi_guardian.sensor import GuardianStatus
from custom_components.unifi_guardian.switch import GuardianSwitch

UUID = "12345678-1234-4234-8234-123456789abc"
MAC = "02:00:00:00:00:01"
DATA = {
    "host": "unifi",
    "port": 443,
    "username": "test",
    "password": "secret",
    "verify_ssl": True,
    "site": "default",
    "uuid": UUID,
    "initial_mac": MAC,
}


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    yield instance
    await instance.async_stop(force=True)


def make_flow(hass):
    flow = GuardianConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    return flow


def api_connection(api):
    @asynccontextmanager
    async def connect(hass, data):
        yield api

    return connect


async def test_setup_enrolls_live_uuid_without_writes(hass):
    flow = make_flow(hass)
    api = SimpleNamespace(
        sites=AsyncMock(return_value=[{"name": "default", "role": "admin"}]),
        active=AsyncMock(return_value={MAC: Client(MAC, "192.0.2.10", "TEST-PC")}),
        set_blocked=AsyncMock(),
    )
    with (
        patch(
            "custom_components.unifi_guardian.config_flow.connection",
            api_connection(api),
        ),
        patch(
            "custom_components.unifi_guardian.config_flow.probe",
            AsyncMock(return_value={UUID}),
        ),
    ):
        result = await flow.async_step_user(DATA)
        assert result["step_id"] == "site"
        result = await flow.async_step_site({"site": "default"})
        assert result["step_id"] == "target"
        result = await flow.async_step_target({"client": MAC})
        assert result["step_id"] == "confirm"
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        result = await flow.async_step_confirm({"uuid": UUID, "name": "Test PC"})
        assert result["data"]["initial_mac"] == MAC
        assert result["data"]["uuid"] == UUID
        assert result["data"]["password"] == "secret"
        api.set_blocked.assert_not_awaited()


async def test_setup_auth_failure_shows_form(hass):
    flow = make_flow(hass)
    api = SimpleNamespace(sites=AsyncMock(side_effect=Unauthorized()))
    with patch(
        "custom_components.unifi_guardian.config_flow.connection", api_connection(api)
    ):
        result = await flow.async_step_user(DATA)
    assert result["errors"] == {"base": "invalid_auth"}


async def test_read_only_account_is_rejected(hass):
    flow = make_flow(hass)
    api = SimpleNamespace(
        sites=AsyncMock(return_value=[{"name": "default", "role": "readonly"}])
    )
    with patch(
        "custom_components.unifi_guardian.config_flow.connection", api_connection(api)
    ):
        result = await flow.async_step_user(DATA)
    assert result["errors"] == {"base": "no_permission"}


async def test_discovery_failure_does_not_enroll(hass):
    flow = make_flow(hass)
    client = Client(MAC, "192.0.2.10")
    flow._data = DATA.copy()
    flow._clients = {MAC: client}
    api = SimpleNamespace(active=AsyncMock(return_value={MAC: client}))
    with (
        patch(
            "custom_components.unifi_guardian.config_flow.connection",
            api_connection(api),
        ),
        patch(
            "custom_components.unifi_guardian.config_flow.probe",
            AsyncMock(return_value=set()),
        ),
    ):
        result = await flow.async_step_target({"client": MAC})
    assert result["errors"] == {"base": "discovery_failed"}


def coordinator(hass):
    entry = SimpleNamespace(
        entry_id="test", data=DATA, title="Test PC", async_on_unload=MagicMock()
    )
    api = SimpleNamespace(
        records=AsyncMock(), active=AsyncMock(), set_blocked=AsyncMock()
    )
    result = GuardianCoordinator(hass, entry, api)
    result.store.async_save = AsyncMock()
    result.engine.save = result.store.async_save
    return result


async def test_switch_means_block_not_allow(hass):
    hub = coordinator(hass)
    hub.engine.state = State(known=[MAC])
    hub.engine.api.records.side_effect = [
        {MAC: Client(MAC)},
        {MAC: Client(MAC, blocked=True)},
        {MAC: Client(MAC, blocked=True)},
        {MAC: Client(MAC)},
    ]
    switch = GuardianSwitch(hub)
    sensor = GuardianStatus(hub)
    await switch.async_turn_on()
    assert switch.is_on
    assert sensor.native_value == "known_macs_blocked"
    hub.engine.api.set_blocked.assert_awaited_with(MAC, True)
    await switch.async_turn_off()
    assert not switch.is_on
    assert sensor.native_value == "guardian_blocks_released"
    hub.engine.api.set_blocked.assert_awaited_with(MAC, False)
    await hub.async_shutdown()


async def test_outage_persists_intent_but_sensor_is_unavailable(hass):
    hub = coordinator(hass)
    hub.engine.api.records.side_effect = TimeoutError()
    switch = GuardianSwitch(hub)
    sensor = GuardianStatus(hub)
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()
    assert switch.is_on
    assert switch.available
    assert not sensor.available
    assert hub.store.async_save.call_args.args[0]["requested"] is True
    await hub.async_shutdown()


async def test_load_restores_requested_state_and_owned_macs(hass):
    hub = coordinator(hass)
    hub.store.async_load = AsyncMock(
        return_value={
            "requested": True,
            "known": [MAC],
            "owned": [MAC],
            "last_identified": None,
        }
    )
    await hub.load()
    assert hub.engine.state.requested
    assert hub.engine.state.owned == [MAC]
    await hub.async_shutdown()
