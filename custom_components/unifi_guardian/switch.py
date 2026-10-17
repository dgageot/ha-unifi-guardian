"""The switch means requested blocking, not verified enforcement."""

from homeassistant.components.switch import SwitchEntity

from .entity import GuardianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator, _ = entry.runtime_data
    async_add_entities([GuardianSwitch(coordinator)])


class GuardianSwitch(GuardianEntity, SwitchEntity):
    _attr_name = "Block PC"
    _attr_icon = "mdi:shield-lock"

    def __init__(self, coordinator):
        super().__init__(coordinator, "block")

    @property
    def available(self):
        # Permit changing the persisted request even during controller outages.
        return True

    @property
    def is_on(self):
        return self.coordinator.engine.state.requested

    @property
    def extra_state_attributes(self):
        return {
            "state_meaning": "requested_blocking",
            "controller_available": self.coordinator.last_update_success,
        }

    async def async_turn_on(self, **kwargs):
        await self.coordinator.set_requested(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.set_requested(False)
