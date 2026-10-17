"""Report controller confirmation separately from requested state."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .entity import GuardianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator, _ = entry.runtime_data
    async_add_entities([GuardianStatus(coordinator)])


class GuardianStatus(GuardianEntity, SensorEntity):
    _attr_name = "Enforcement"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "not_identified",
        "known_macs_blocked",
        "block_pending",
        "unblock_pending",
        "external_block",
        "guardian_blocks_released",
    ]

    def __init__(self, coordinator):
        super().__init__(coordinator, "enforcement")

    @property
    def native_value(self):
        return self.coordinator.engine.status

    @property
    def extra_state_attributes(self):
        engine = self.coordinator.engine
        return {
            "uuid": engine.target_uuid,
            "known_macs": list(engine.state.known),
            "guardian_owned_blocks": list(engine.state.owned),
            "last_identified": engine.state.last_identified,
            "discovery_visible": engine.visible,
            "scope": "known MACs only; new identities may evade discovery",
        }
