"""stdio MCP for local FRITZ!Box mesh administration."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from fritz_mesh_mcp import tr064
from fritz_mesh_mcp.client import FritzClient, boxes_from_env

mcp = MCPServer("fritz-mesh")
_client: FritzClient | None = None


def client() -> FritzClient:
    global _client
    if _client is None:
        _client = FritzClient(boxes_from_env())
    return _client


def _yn(enabled: bool) -> str:
    return "on" if enabled else "off"


@mcp.tool()
def fritz_mesh_status() -> dict:
    """Read the master and both repeaters: adoption, SSID, steering, channel mode, and power."""
    return client().mesh_status()


@mcp.tool()
def fritz_list_devices() -> list[dict]:
    """List devices known to the mesh master, including band, parent, and IP."""
    return client().list_devices()


@mcp.tool()
def fritz_get_device(uid: str) -> dict:
    """Read one device. uid is the FRITZ id, for example landevice1."""
    return client().get_device(uid)


@mcp.tool()
def fritz_get_radio(host: str | None = None) -> dict:
    """Read band steering, channel mode, channels, and transmit power. host defaults to the master."""
    return client().get_radio(host)


@mcp.tool()
def fritz_set_band_steering(enabled: bool) -> dict:
    """Turn client band steering on or off on the master, keeping channel mode and power as they are."""
    return client().update_radio(bandsteering=_yn(enabled))


@mcp.tool()
def fritz_set_channel_mode(mode: str, channel_24: int | None = None, channel_5: int | None = None) -> dict:
    """Set channel selection to auto or manual. Manual may include a 2.4 GHz and a 5 GHz channel."""
    if mode not in {"auto", "manual"}:
        raise ValueError("mode must be auto or manual.")
    changes = {"channelSelectMode": mode}
    if channel_24 is not None:
        changes["chan24ghz"] = str(channel_24)
    if channel_5 is not None:
        changes["chan5ghz"] = str(channel_5)
    return client().update_radio(**changes)


@mcp.tool()
def fritz_set_transmit_power(step: int) -> dict:
    """Set transmit power. 1 is 100%, then 50%, 25%, 12%, and 6%."""
    if step not in {1, 2, 3, 4, 5}:
        raise ValueError("step must be 1, 2, 3, 4, or 5.")
    return client().update_radio(autopowerlevel=str(step))


@mcp.tool()
def fritz_set_coexistence(enabled: bool) -> dict:
    """Turn 2.4 GHz Wi-Fi coexistence on or off without changing steering, channel, or power."""
    return client().update_radio(coexist=_yn(enabled))


@mcp.tool()
def fritz_set_backhaul_steering(enabled: bool) -> dict:
    """Turn mesh backhaul steering on or off. This is separate from client band steering."""
    return client().set_backhaul_steering(enabled)


@mcp.tool()
def fritz_reserve_ipv4(uid: str, reserve: bool = True, ip: str | None = None) -> dict:
    """Reserve or release the IPv4 address of one device. Pass ip to pin a specific address."""
    return client().reserve_ipv4(uid, reserve, ip)


@mcp.tool()
def fritz_connection_status(host: str | None = None) -> dict:
    """WAN state from TR-064: model, external address, uptime, and whether an update is offered."""
    return tr064.connection_status(client().tr064(host))


@mcp.tool()
def fritz_wifi_networks(host: str | None = None) -> list[dict]:
    """SSIDs, channels, and bands from TR-064. Wi-Fi passwords are not included."""
    return tr064.wifi_networks(client().tr064(host))


@mcp.tool()
def fritz_lan_dhcp(host: str | None = None) -> dict:
    """DHCP range, mask, and DNS. Per-device reservations use fritz_reserve_ipv4."""
    return tr064.lan_dhcp(client().tr064(host))


@mcp.tool()
def fritz_system_log(limit: int = 30, host: str | None = None) -> list:
    """Recent system log lines from the master, or from host."""
    return tr064.system_log(client().tr064(host), limit)


@mcp.tool()
def fritz_port_forwards(host: str | None = None) -> list[dict]:
    """Active IPv4 port-forwarding rules."""
    return tr064.port_forwards(client().tr064(host))


@mcp.tool()
def fritz_set_guest_wifi(enabled: bool) -> dict:
    """Enable or disable the guest Wi-Fi network on the master."""
    return tr064.set_guest_wifi(client().tr064(), enabled)


@mcp.tool()
def fritz_set_wan_access(ip_address: str, blocked: bool) -> dict:
    """Block or restore one device's internet access by IPv4 address."""
    return tr064.set_wan_access(client().tr064(), ip_address, blocked)


@mcp.tool()
def fritz_set_upnp(enabled: bool) -> dict:
    """Enable or disable UPnP port forwarding. The media server stays off."""
    return tr064.set_upnp(client().tr064(), enabled)


@mcp.tool()
def fritz_wake_on_lan(mac_address: str) -> dict:
    """Ask the master to send a Wake-on-LAN packet."""
    return tr064.wake_on_lan(client().tr064(), mac_address)


@mcp.tool()
def fritz_smart_home_devices() -> list[dict]:
    """DECT smart-home devices the master can see."""
    return tr064.smart_home_devices(client().tr064())


@mcp.tool()
def fritz_set_smart_home_switch(ain: str, on: bool) -> dict:
    """Switch a smart-home actuator by its AIN."""
    return tr064.set_smart_home_switch(client().tr064(), ain, on)


@mcp.tool()
def fritz_reboot() -> dict:
    """Reboot the master. The network drops for about two minutes."""
    return tr064.reboot(client().tr064())


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
