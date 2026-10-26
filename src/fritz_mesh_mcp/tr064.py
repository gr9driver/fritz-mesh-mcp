"""Named TR-064 reads and writes. Wi-Fi keys are never returned."""

from __future__ import annotations

from fritzconnection import FritzConnection
from fritzconnection.core.exceptions import FritzConnectionException
from fritzconnection.lib.fritzhomeauto import FritzHomeAutomation
from fritzconnection.lib.fritzstatus import FritzStatus

from fritz_mesh_mcp.client import Box, FritzError


def connect(box: Box) -> FritzConnection:
    try:
        return FritzConnection(address=box.host, user=box.user, password=box.password, timeout=12)
    except FritzConnectionException as error:
        raise FritzError(f"TR-064 login to {box.host} failed: {error}") from error


def _call(fc: FritzConnection, service: str, action: str, **arguments):
    try:
        return fc.call_action(service, action, **arguments)
    except FritzConnectionException as error:
        raise FritzError(f"{service}.{action} failed: {error}") from error


def connection_status(fc: FritzConnection) -> dict:
    status = FritzStatus(fc=fc)
    return {
        "model": status.modelname,
        "connected": status.is_connected,
        "external_ip": status.external_ip,
        "uptime": status.str_uptime,
        "update_available": status.update_available,
    }


def wifi_networks(fc: FritzConnection) -> list[dict]:
    networks = []
    for index in range(1, 5):
        service = f"WLANConfiguration{index}"
        try:
            info = fc.call_action(service, "GetInfo")
            channel = fc.call_action(service, "GetChannelInfo")
        except Exception:
            break
        networks.append(
            {
                "index": index,
                "ssid": info.get("NewSSID", ""),
                "enabled": info.get("NewEnable"),
                "channel": info.get("NewChannel"),
                "standard": info.get("NewStandard", ""),
                "mac": info.get("NewBSSID", ""),
                "auto_channel": channel.get("NewX_AVM-DE_AutoChannelEnabled"),
                "band": channel.get("NewX_AVM-DE_FrequencyBand", ""),
            }
        )
    return networks


def lan_dhcp(fc: FritzConnection) -> dict:
    info = _call(fc, "LANHostConfigManagement1", "GetInfo")
    return {
        "dhcp_enabled": info.get("NewDHCPServerEnable"),
        "min_address": info.get("NewMinAddress", ""),
        "max_address": info.get("NewMaxAddress", ""),
        "subnet_mask": info.get("NewSubnetMask", ""),
        "dns_servers": info.get("NewDNSServers", ""),
        "reserved_addresses": info.get("NewReservedAddresses", ""),
    }


def system_log(fc: FritzConnection, limit: int = 30) -> list:
    entries = FritzStatus(fc=fc).get_avm_device_log() or []
    return list(entries[:limit])


def port_forwards(fc: FritzConnection) -> list[dict]:
    count = int(_call(fc, "WANIPConnection1", "GetPortMappingNumberOfEntries").get("NewPortMappingNumberOfEntries", 0))
    rules = []
    for index in range(count):
        entry = _call(fc, "WANIPConnection1", "GetGenericPortMappingEntry", NewPortMappingIndex=index)
        rules.append(
            {
                "protocol": entry.get("NewProtocol", ""),
                "external_port": entry.get("NewExternalPort"),
                "internal_host": entry.get("NewInternalClient", ""),
                "internal_port": entry.get("NewInternalPort"),
                "enabled": entry.get("NewEnabled"),
                "description": entry.get("NewPortMappingDescription", ""),
            }
        )
    return rules


def set_guest_wifi(fc: FritzConnection, enabled: bool) -> dict:
    action = "Enable" if enabled else "Disable"
    _call(fc, "WLANConfiguration3", action)
    info = _call(fc, "WLANConfiguration3", "GetInfo")
    return {"guest_enabled": info.get("NewEnable"), "ssid": info.get("NewSSID", "")}


def set_wan_access(fc: FritzConnection, ip_address: str, blocked: bool) -> dict:
    _call(
        fc,
        "X_AVM-DE_HostFilter1",
        "DisallowWANAccessByIP",
        NewIPv4Address=ip_address,
        NewDisallow=blocked,
    )
    check = _call(fc, "X_AVM-DE_HostFilter1", "GetWANAccessByIP", NewIPv4Address=ip_address)
    return {"ip": ip_address, "wan_blocked": check.get("NewDisallow")}


def set_upnp(fc: FritzConnection, enabled: bool) -> dict:
    _call(fc, "X_AVM-DE_UPnP1", "SetConfig", NewEnable=enabled, NewUPnPMediaServer=False)
    info = _call(fc, "X_AVM-DE_UPnP1", "GetInfo")
    return {"upnp_enabled": info.get("NewEnable")}


def wake_on_lan(fc: FritzConnection, mac_address: str) -> dict:
    _call(fc, "Hosts1", "X_AVM-DE_WakeOnLANByMACAddress", NewMACAddress=mac_address)
    return {"mac": mac_address, "sent": True}


def smart_home_devices(fc: FritzConnection) -> list[dict]:
    devices = []
    for device in FritzHomeAutomation(fc=fc).get_device_information_list():
        devices.append(
            {
                "ain": device.get("NewAIN", ""),
                "name": device.get("NewDeviceName", ""),
                "present": device.get("NewPresent") == "CONNECTED",
                "switch_state": device.get("NewSwitchState") or None,
            }
        )
    return devices


def set_smart_home_switch(fc: FritzConnection, ain: str, on: bool) -> dict:
    FritzHomeAutomation(fc=fc).set_switch(ain, on)
    return {"ain": ain, "on": on}


def reboot(fc: FritzConnection) -> dict:
    fc.reboot()
    return {"rebooting": True}
