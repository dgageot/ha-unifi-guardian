"""Persistent identity matching and block reconciliation."""

import asyncio
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from .discovery import probe


@dataclass
class State:
    requested: bool = False
    known: list[str] = field(default_factory=list)
    owned: list[str] = field(default_factory=list)
    last_identified: str | None = None


class Engine:
    def __init__(self, api, target_uuid, state, save, discover=probe):
        self.api = api
        self.target_uuid = target_uuid
        self.state = state
        self.save = save
        self.discover = discover
        self.lock = asyncio.Lock()
        self.status = "not_identified"
        self.visible = False

    async def persist(self):
        await self.save(asdict(self.state))

    async def request(self, blocked: bool):
        async with self.lock:
            previous = self.state.requested
            self.state.requested = blocked
            try:
                await self.persist()
            except BaseException:
                self.state.requested = previous
                raise
            await self.reconcile()

    async def update(self):
        async with self.lock:
            # Enforce remembered identities before spending time on discovery.
            await self.reconcile()
            active = await self.api.active()
            counts = Counter(c.ip for c in active.values() if c.ip)
            candidates = [
                c
                for c in active.values()
                if c.ip and not c.wired and not c.blocked and counts[c.ip] == 1
            ]
            semaphore = asyncio.Semaphore(8)

            async def check(client):
                async with semaphore:
                    uuids = await self.discover(client.ip)
                return client, self.target_uuid in uuids

            matches = [
                c
                for c, matched in await asyncio.gather(*(check(c) for c in candidates))
                if matched
            ]
            self.visible = False
            if matches:
                fresh = await self.api.active()
                fresh_counts = Counter(c.ip for c in fresh.values() if c.ip)
                for client in matches:
                    current = fresh.get(client.mac)
                    if (
                        current
                        and current.ip == client.ip
                        and not current.wired
                        and fresh_counts[current.ip] == 1
                    ):
                        if client.mac not in self.state.known:
                            self.state.known.append(client.mac)
                        self.visible = True
                if self.visible:
                    self.state.last_identified = datetime.now(UTC).isoformat()
                    await self.persist()
            await self.reconcile()

    async def reconcile(self):
        records = await self.api.records()
        if self.state.requested:
            for mac in self.state.known:
                record = records.get(mac)
                if record is None or record.blocked:
                    continue
                if mac not in self.state.owned:
                    self.state.owned.append(mac)
                # Journal every attempt, including retries after a failed disk write.
                await self.persist()
                await self.api.set_blocked(mac, True)
        else:
            for mac in list(self.state.owned):
                record = records.get(mac)
                if record is None:
                    continue
                if record.blocked:
                    await self.api.set_blocked(mac, False)
        confirmed = await self.api.records()
        if not self.state.requested:
            released = [
                mac
                for mac in self.state.owned
                if mac in confirmed and not confirmed[mac].blocked
            ]
            if released:
                self.state.owned = [
                    mac for mac in self.state.owned if mac not in released
                ]
                await self.persist()
        if not self.state.known:
            self.status = "not_identified"
        elif self.state.requested:
            self.status = (
                "known_macs_blocked"
                if all(
                    mac in confirmed and confirmed[mac].blocked
                    for mac in self.state.known
                )
                else "block_pending"
            )
        elif self.state.owned:
            self.status = "unblock_pending"
        elif any(
            confirmed.get(mac) and confirmed[mac].blocked for mac in self.state.known
        ):
            self.status = "external_block"
        else:
            self.status = "guardian_blocks_released"
