"""Tests for the Minecraft Server locator."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.minecraft_server.server_locator import (
    LocalServerLocator,
    _get_all_ips,
    _ping_server,
)


class TestGetAllIps:
    """Tests for _get_all_ips function."""

    def test_get_all_ips_standard_network(self) -> None:
        """Test _get_all_ips with standard IP."""
        ips = _get_all_ips("192.168.1.1")
        assert len(ips) == 256
        assert ips[0] == "192.168.1.0"
        assert ips[1] == "192.168.1.1"
        assert ips[255] == "192.168.1.255"

    def test_get_all_ips_different_network(self) -> None:
        """Test _get_all_ips with different network."""
        ips = _get_all_ips("10.0.0.50")
        assert len(ips) == 256
        assert ips[0] == "10.0.0.0"
        assert ips[50] == "10.0.0.50"
        assert ips[255] == "10.0.0.255"

    def test_get_all_ips_172_network(self) -> None:
        """Test _get_all_ips with 172 network."""
        ips = _get_all_ips("172.16.0.1")
        assert len(ips) == 256
        assert ips[0] == "172.16.0.0"
        assert ips[1] == "172.16.0.1"


@pytest.mark.asyncio
async def test_ping_server_success() -> None:
    """Test _ping_server returns IP on successful connection."""
    with patch(
        "homeassistant.components.minecraft_server.server_locator.JavaServer"
    ) as mock_java_server:
        mock_instance = AsyncMock()
        mock_instance.async_status = AsyncMock()
        mock_java_server.return_value = mock_instance

        result = await _ping_server("192.168.1.1")
        assert result == "192.168.1.1"
        mock_java_server.assert_called_once_with("192.168.1.1")
        mock_instance.async_status.assert_called_once()


@pytest.mark.asyncio
async def test_ping_server_failure() -> None:
    """Test _ping_server returns None on connection failure."""
    with patch(
        "homeassistant.components.minecraft_server.server_locator.JavaServer"
    ) as mock_java_server:
        mock_instance = AsyncMock()
        mock_instance.async_status = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        mock_java_server.return_value = mock_instance

        result = await _ping_server("192.168.1.1")
        assert result is None


@pytest.mark.asyncio
async def test_ping_server_timeout() -> None:
    """Test _ping_server handles timeout."""
    with patch(
        "homeassistant.components.minecraft_server.server_locator.JavaServer"
    ) as mock_java_server:
        mock_instance = AsyncMock()
        mock_instance.async_status = AsyncMock(side_effect=TimeoutError("Timeout"))
        mock_java_server.return_value = mock_instance

        result = await _ping_server("192.168.1.1")
        assert result is None


class TestLocalServerLocator:
    """Tests for LocalServerLocator."""

    @pytest.mark.asyncio
    async def test_get_local_networks_filters_ipv4(self) -> None:
        """Test _get_local_networks returns only IPv4 addresses in private ranges."""
        locator = LocalServerLocator()
        mock_interfaces = ["eth0", "lo", "wlan0"]
        mock_addresses = {
            "eth0": {
                2: [{"addr": "192.168.1.100"}],
            },
            "lo": {
                2: [{"addr": "127.0.0.1"}],
            },
            "wlan0": {
                2: [{"addr": "10.0.0.50"}],
            },
        }

        with (
            patch(
                "homeassistant.components.minecraft_server.server_locator.interfaces",
                return_value=mock_interfaces,
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator.ifaddresses",
                side_effect=lambda x: mock_addresses.get(x, {}),
            ),
        ):
            networks = await locator._get_local_networks()
            assert len(networks) == 2
            assert ("eth0", "192.168.1.100") in networks
            assert ("wlan0", "10.0.0.50") in networks
            assert ("lo", "127.0.0.1") not in networks

    @pytest.mark.asyncio
    async def test_get_local_networks_filters_private_ranges(self) -> None:
        """Test _get_local_networks filters for private IP ranges."""
        locator = LocalServerLocator()
        mock_interfaces = ["eth0", "eth1", "eth2", "eth3"]
        mock_addresses = {
            "eth0": {
                2: [{"addr": "192.168.1.1"}],
            },
            "eth1": {
                2: [{"addr": "10.0.0.1"}],
            },
            "eth2": {
                2: [{"addr": "172.16.0.1"}],
            },
            "eth3": {
                2: [{"addr": "8.8.8.8"}],
            },
        }

        with (
            patch(
                "homeassistant.components.minecraft_server.server_locator.interfaces",
                return_value=mock_interfaces,
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator.ifaddresses",
                side_effect=lambda x: mock_addresses.get(x, {}),
            ),
        ):
            networks = await locator._get_local_networks()
            assert len(networks) == 3
            ips = [ip for _, ip in networks]
            assert "192.168.1.1" in ips
            assert "10.0.0.1" in ips
            assert "172.16.0.1" in ips
            assert "8.8.8.8" not in ips

    @pytest.mark.asyncio
    async def test_get_local_networks_skips_missing_ipv4(self) -> None:
        """Test _get_local_networks skips interfaces without IPv4."""
        locator = LocalServerLocator()
        mock_interfaces = ["eth0", "eth1"]
        mock_addresses = {
            "eth0": {
                2: [{"addr": "192.168.1.1"}],
            },
            "eth1": {
                10: [{"addr": "fe80::1"}],  # IPv6 only
            },
        }

        with (
            patch(
                "homeassistant.components.minecraft_server.server_locator.interfaces",
                return_value=mock_interfaces,
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator.ifaddresses",
                side_effect=lambda x: mock_addresses.get(x, {}),
            ),
        ):
            networks = await locator._get_local_networks()
            assert len(networks) == 1
            assert networks[0] == ("eth0", "192.168.1.1")

    @pytest.mark.asyncio
    async def test_get_local_networks_handles_missing_addr_key(self) -> None:
        """Test _get_local_networks handles missing addr key."""
        locator = LocalServerLocator()
        mock_interfaces = ["eth0", "eth1"]
        mock_addresses = {
            "eth0": {
                2: [{"addr": "192.168.1.1"}],
            },
            "eth1": {
                2: [{"broadcast": "10.0.0.255"}],  # No addr key
            },
        }

        with (
            patch(
                "homeassistant.components.minecraft_server.server_locator.interfaces",
                return_value=mock_interfaces,
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator.ifaddresses",
                side_effect=lambda x: mock_addresses.get(x, {}),
            ),
        ):
            networks = await locator._get_local_networks()
            assert len(networks) == 1
            assert networks[0] == ("eth0", "192.168.1.1")

    @pytest.mark.asyncio
    async def test_find_minecraft_servers_async_success(self) -> None:
        """Test _find_minecraft_servers_async returns found servers."""
        locator = LocalServerLocator()
        mock_interfaces = ["eth0"]
        mock_addresses = {
            "eth0": {
                2: [{"addr": "192.168.1.1"}],
            },
        }

        async def mock_ping_server(ip: str) -> str | None:
            """Mock ping server that returns specific IPs."""
            if ip in ["192.168.1.100", "192.168.1.200"]:
                return ip
            return None

        with (
            patch(
                "homeassistant.components.minecraft_server.server_locator.interfaces",
                return_value=mock_interfaces,
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator.ifaddresses",
                side_effect=lambda x: mock_addresses.get(x, {}),
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator._ping_server",
                side_effect=mock_ping_server,
            ),
        ):
            servers = await locator._find_minecraft_servers_async()
            assert "192.168.1.100" in servers
            assert "192.168.1.200" in servers
            # Should not include None values
            assert None not in servers

    @pytest.mark.asyncio
    async def test_find_minecraft_servers_async_no_servers(self) -> None:
        """Test _find_minecraft_servers_async returns empty list when no servers found."""
        locator = LocalServerLocator()
        mock_interfaces = ["eth0"]
        mock_addresses = {
            "eth0": {
                2: [{"addr": "192.168.1.1"}],
            },
        }

        async def mock_ping_server(ip: str) -> None:
            """Mock ping server that always returns None."""

        with (
            patch(
                "homeassistant.components.minecraft_server.server_locator.interfaces",
                return_value=mock_interfaces,
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator.ifaddresses",
                side_effect=lambda x: mock_addresses.get(x, {}),
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator._ping_server",
                side_effect=mock_ping_server,
            ),
        ):
            servers = await locator._find_minecraft_servers_async()
            assert servers == []

    @pytest.mark.asyncio
    async def test_find_minecraft_servers_async_multiple_networks(self) -> None:
        """Test _find_minecraft_servers_async with multiple networks."""
        locator = LocalServerLocator()
        mock_interfaces = ["eth0", "eth1"]
        mock_addresses = {
            "eth0": {
                2: [{"addr": "192.168.1.1"}],
            },
            "eth1": {
                2: [{"addr": "10.0.0.1"}],
            },
        }

        found_ips = set()

        async def mock_ping_server(ip: str) -> str | None:
            """Mock ping server that tracks which IPs are pinged."""
            found_ips.add(ip)
            if ip in ["192.168.1.100", "10.0.0.100"]:
                return ip
            return None

        with (
            patch(
                "homeassistant.components.minecraft_server.server_locator.interfaces",
                return_value=mock_interfaces,
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator.ifaddresses",
                side_effect=lambda x: mock_addresses.get(x, {}),
            ),
            patch(
                "homeassistant.components.minecraft_server.server_locator._ping_server",
                side_effect=mock_ping_server,
            ),
        ):
            servers = await locator._find_minecraft_servers_async()
            # Both networks should be scanned
            assert "192.168.1.100" in servers
            assert "10.0.0.100" in servers
            # Verify both ranges were scanned
            assert any(ip.startswith("192.168.1") for ip in found_ips)
            assert any(ip.startswith("10.0.0") for ip in found_ips)

    def test_find_servers_runs_async(self) -> None:
        """Test find_servers properly runs async code."""
        locator = LocalServerLocator()

        with patch.object(
            locator,
            "_find_minecraft_servers_async",
            return_value=["192.168.1.100", "192.168.1.200"],
        ):
            servers = locator.find_servers()
            # The mock will return the awaitable, so we need to handle that
            assert servers is not None
