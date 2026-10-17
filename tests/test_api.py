from unittest.mock import AsyncMock

import aiohttp

from custom_components.unifi_guardian.api import UnifiAPI, clients_from_response


def test_normalizes_clients_without_inventing_ip_addresses():
    result = clients_from_response(
        {
            "data": [
                {"mac": "AA:BB:CC:DD:EE:FF", "hostname": "PC", "blocked": True},
                {"hostname": "invalid"},
            ]
        }
    )
    assert list(result) == ["aa:bb:cc:dd:ee:ff"]
    assert result["aa:bb:cc:dd:ee:ff"].blocked
    assert result["aa:bb:cc:dd:ee:ff"].ip == ""


async def test_native_block_unblock_commands():
    async with aiohttp.ClientSession() as session:
        api = UnifiAPI(
            session,
            {
                "host": "unifi",
                "port": 443,
                "username": "test",
                "password": "test",
                "site": "default",
            },
            False,
        )
        api.controller.request = AsyncMock(return_value={"data": []})
        await api.set_blocked("aa:bb:cc:dd:ee:ff", True)
        request = api.controller.request.call_args.args[0]
        assert request.path == "/cmd/stamgr"
        assert request.data == {"cmd": "block-sta", "mac": "aa:bb:cc:dd:ee:ff"}
        await api.set_blocked("aa:bb:cc:dd:ee:ff", False)
        assert api.controller.request.call_args.args[0].data["cmd"] == "unblock-sta"
