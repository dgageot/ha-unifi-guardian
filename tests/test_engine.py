from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from custom_components.unifi_guardian.api import Client
from custom_components.unifi_guardian.engine import Engine, State

UUID = "12345678-1234-4234-8234-123456789abc"
OLD = "02:00:00:00:00:01"
NEW = "02:00:00:00:00:02"
OTHER = "02:00:00:00:00:03"


class FakeAPI:
    def __init__(self, clients=()):
        self.rows = {c.mac: c for c in clients}
        self.online = dict(self.rows)
        self.commands = []
        self.fail_after_write = False
        self.apply = True

    async def active(self):
        return dict(self.online)

    async def records(self):
        return dict(self.rows)

    async def set_blocked(self, mac, blocked):
        self.commands.append((mac, blocked))
        if self.apply:
            self.rows[mac] = replace(self.rows[mac], blocked=blocked)
        if self.fail_after_write:
            raise TimeoutError


def engine(api, state=None, discover=None):
    return Engine(
        api,
        UUID,
        state or State(),
        AsyncMock(),
        discover or AsyncMock(return_value=set()),
    )


async def test_observation_never_blocks():
    api = FakeAPI([Client(OLD, "192.0.2.10")])
    guardian = engine(api, discover=AsyncMock(return_value={UUID}))
    await guardian.update()
    assert guardian.state.known == [OLD]
    assert guardian.state.last_identified
    assert guardian.visible
    assert not api.commands


async def test_rotated_mac_is_blocked_and_unknown_client_is_not():
    api = FakeAPI([Client(OLD), Client(NEW, "192.0.2.20"), Client(OTHER, "192.0.2.30")])

    async def discover(ip):
        return {UUID} if ip == "192.0.2.20" else set()

    guardian = engine(api, State(requested=True, known=[OLD]), discover)
    await guardian.update()
    assert guardian.state.known == [OLD, NEW]
    assert api.commands == [(OLD, True), (NEW, True)]
    assert guardian.status == "known_macs_blocked"


async def test_discovery_disappearance_does_not_unblock():
    api = FakeAPI([Client(OLD, blocked=True)])
    guardian = engine(api, State(requested=True, known=[OLD], owned=[OLD]))
    await guardian.update()
    assert guardian.state.known == [OLD]
    assert not api.commands
    assert not guardian.visible


async def test_restart_can_unblock_offline_client():
    api = FakeAPI([Client(OLD)])
    guardian = engine(api, State(known=[OLD]))
    await guardian.request(True)
    saved = deepcopy(guardian.save.call_args.args[0])
    api.online = {}
    restarted = engine(api, State(**saved))
    await restarted.request(False)
    assert api.commands == [(OLD, True), (OLD, False)]
    assert restarted.state.owned == []
    assert restarted.status == "guardian_blocks_released"


async def test_preexisting_block_is_not_owned_or_removed():
    api = FakeAPI([Client(OLD, blocked=True)])
    guardian = engine(api, State(known=[OLD]))
    await guardian.request(True)
    assert guardian.state.owned == []
    await guardian.request(False)
    assert not api.commands
    assert guardian.status == "external_block"


async def test_lost_command_response_is_recoverable_after_restart():
    api = FakeAPI([Client(OLD)])
    api.fail_after_write = True
    guardian = engine(api, State(known=[OLD]))
    with pytest.raises(TimeoutError):
        await guardian.request(True)
    saved = deepcopy(guardian.save.call_args.args[0])
    assert saved["owned"] == [OLD]
    api.fail_after_write = False
    restarted = engine(api, State(**saved))
    await restarted.request(False)
    assert not api.rows[OLD].blocked
    assert not restarted.state.owned


async def test_mapping_change_during_discovery_is_rejected():
    api = FakeAPI([Client(NEW, "192.0.2.10")])

    async def discover(ip):
        api.online = {OTHER: Client(OTHER, ip)}
        return {UUID}

    guardian = engine(api, State(requested=True), discover)
    await guardian.update()
    assert not guardian.state.known
    assert not api.commands


async def test_duplicate_ip_is_not_probed():
    api = FakeAPI([Client(OLD, "192.0.2.10"), Client(OTHER, "192.0.2.10")])
    discover = AsyncMock(return_value={UUID})
    guardian = engine(api, discover=discover)
    await guardian.update()
    discover.assert_not_awaited()
    assert not guardian.state.known


async def test_acknowledgement_without_state_change_is_pending():
    api = FakeAPI([Client(OLD)])
    api.apply = False
    guardian = engine(api, State(known=[OLD]))
    await guardian.request(True)
    assert guardian.status == "block_pending"


async def test_unblock_without_confirmation_retains_ownership():
    api = FakeAPI([Client(OLD, blocked=True)])
    api.apply = False
    guardian = engine(api, State(requested=True, known=[OLD], owned=[OLD]))
    await guardian.request(False)
    assert guardian.status == "unblock_pending"
    assert guardian.state.owned == [OLD]


async def test_missing_record_does_not_claim_block_success():
    guardian = engine(FakeAPI(), State(known=[OLD]))
    await guardian.request(True)
    assert guardian.status == "block_pending"


async def test_missing_record_does_not_forget_owned_block():
    guardian = engine(FakeAPI(), State(known=[OLD], owned=[OLD]))
    await guardian.request(False)
    assert guardian.status == "unblock_pending"
    assert guardian.state.owned == [OLD]


async def test_unknown_uuid_is_not_enrolled():
    api = FakeAPI([Client(NEW, "192.0.2.20")])
    guardian = engine(api, State(requested=True), AsyncMock(return_value={"other"}))
    await guardian.update()
    assert not guardian.state.known
    assert not api.commands


async def test_manual_unblock_is_reapplied_while_requested():
    api = FakeAPI([Client(OLD)])
    guardian = engine(api, State(requested=True, known=[OLD], owned=[OLD]))
    await guardian.update()
    assert api.rows[OLD].blocked


async def test_storage_failure_prevents_block_command():
    api = FakeAPI([Client(OLD)])
    guardian = engine(api, State(known=[OLD]))
    guardian.save.side_effect = OSError("disk unavailable")
    with pytest.raises(OSError):
        await guardian.request(True)
    assert not api.commands


async def test_failed_storage_does_not_change_requested_state():
    guardian = engine(FakeAPI(), State())
    guardian.save.side_effect = OSError("disk unavailable")
    with pytest.raises(OSError):
        await guardian.request(True)
    assert not guardian.state.requested


async def test_failed_ownership_journal_is_retried_before_command():
    api = FakeAPI([Client(OLD)])
    guardian = engine(api, State(requested=True, known=[OLD]))
    guardian.save.side_effect = OSError("disk unavailable")
    with pytest.raises(OSError):
        await guardian.reconcile()
    with pytest.raises(OSError):
        await guardian.reconcile()
    assert not api.commands
    guardian.save.side_effect = None
    await guardian.reconcile()
    assert api.commands == [(OLD, True)]
