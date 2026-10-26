"""FRITZ!Box session, mesh reads, and explicit radio/DHCP writes."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

SECRET_PARTS = ("psk", "password", "passphrase", "pin")


class FritzError(RuntimeError):
    pass


def login_response(challenge: str, password: str) -> str:
    """Answer the challenge the box actually sent.

    ``login_sid.lua?version=2`` returns ``2$iter$salt$iter2$salt2``. The
    response is the second salt plus a second PBKDF2 round. A shorter
    ``2$iter$salt`` challenge uses one round. Anything else is the legacy
    MD5 challenge.
    """
    if challenge.startswith("2$"):
        parts = challenge.split("$")
        password_bytes = password.encode("utf-8")
        if len(parts) >= 5 and parts[3] and parts[4]:
            first = hashlib.pbkdf2_hmac(
                "sha256", password_bytes, bytes.fromhex(parts[2]), int(parts[1])
            )
            second = hashlib.pbkdf2_hmac(
                "sha256", first, bytes.fromhex(parts[4]), int(parts[3])
            )
            return f"{parts[4]}${second.hex()}"
        digest = hashlib.pbkdf2_hmac(
            "sha256", password_bytes, bytes.fromhex(parts[2]), int(parts[1])
        )
        return f"{challenge}${digest.hex()}"
    text = f"{challenge}-{password}".encode("utf-16le")
    return f"{challenge}-{hashlib.md5(text).hexdigest()}"


def redact(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if any(part in key.lower() for part in SECRET_PARTS):
                continue
            cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def radio_form(data: dict, **overrides: str) -> dict[str, str]:
    """Rebuild the channel-page submit from the last read.

    The page saves steering, channel mode, channels, and transmit power
    together. Sending only the checkbox is what previously cleared the
    other two. Every radio write therefore resubmits the snapshot and
    then replaces the requested fields.
    """
    fields: dict[str, str] = {
        "page": "chan",
        "apply": "",
        "channelSelectMode": str(data.get("channelSelectMode") or "auto"),
        "bandsteering": "on" if (data.get("bandSteering") or {}).get("on") else "off",
        "use1213": "on" if (data.get("auto1213") or {}).get("on") else "off",
        "coexist": "on" if (data.get("coexist") or {}).get("on") else "off",
    }
    power = (data.get("powerLevel") or {}).get("current") or ""
    if power:
        fields["autopowerlevel"] = str(power)
    auto_power = data.get("autoPower")
    if isinstance(auto_power, dict):
        fields["autopower"] = "on" if auto_power.get("on") else "off"
    for band in data.get("bands") or []:
        band_data = data.get(band) or {}
        if band_data.get("active"):
            fields[f"bandActive{band}"] = "on"
        fields[f"chan{band}"] = str(band_data.get("currentChannel") or 0)
        mode = band_data.get("currentWlanMode") or ""
        if mode:
            fields[f"wlanMode{band}"] = str(mode)
        fields[f"useable_{band}"] = "1" if band_data.get("useable") else "0"
    fields.update({key: str(value) for key, value in overrides.items()})
    return fields


def radio_summary(data: dict) -> dict:
    bands = []
    for name in data.get("bands") or []:
        band = data.get(name) or {}
        active = [
            channel.get("value")
            for channel in band.get("channels") or []
            if isinstance(channel, dict) and channel.get("active")
        ]
        bands.append(
            {
                "band": name,
                "enabled": bool(band.get("active")),
                "channel": band.get("currentChannel"),
                "active_scan_channels": active,
                "wlan_mode": band.get("currentWlanMode") or "",
            }
        )
    power = data.get("powerLevel") or {}
    return {
        "band_steering": bool((data.get("bandSteering") or {}).get("on")),
        "band_steering_control_enabled": not bool((data.get("bandSteering") or {}).get("disabled")),
        "channel_mode": data.get("channelSelectMode"),
        "power_step": power.get("current") or "",
        "power_steps": [item.get("value") for item in power.get("options") or []],
        "coexistence_24": bool((data.get("coexist") or {}).get("on")),
        "auto_channel_12_13": bool((data.get("auto1213") or {}).get("on")),
        "adopted": bool(data.get("isAdopted")),
        "bands": bands,
    }


@dataclass
class Box:
    name: str
    host: str
    user: str
    password: str


class FritzClient:
    def __init__(self, boxes: list[Box], opener=None):
        if not boxes:
            raise FritzError("No FRITZ!Box is configured.")
        self.boxes = boxes
        self.master = boxes[0]
        self._opener = opener or urllib.request.urlopen
        self._sid: dict[str, str] = {}
        self._tr064: dict[str, object] = {}

    def sid(self, box: Box) -> str:
        cached = self._sid.get(box.host)
        if cached:
            return cached
        url = f"http://{box.host}/login_sid.lua?version=2"
        with self._opener(url, timeout=8) as response:
            root = ET.fromstring(response.read())
        challenge = root.findtext("Challenge") or ""
        payload = urllib.parse.urlencode(
            {"username": box.user, "response": login_response(challenge, box.password)}
        ).encode()
        request = urllib.request.Request(url, data=payload)
        with self._opener(request, timeout=8) as response:
            root = ET.fromstring(response.read())
        sid = root.findtext("SID") or ""
        if not sid or set(sid) == {"0"}:
            block = root.findtext("BlockTime") or "0"
            raise FritzError(f"Login to {box.host} failed (block time {block}s).")
        self._sid[box.host] = sid
        return sid

    def data(self, box: Box, page: str, extra: dict | None = None) -> dict:
        fields = {"sid": self.sid(box), "xhr": "1", "lang": "en", "page": page}
        if extra:
            fields.update(extra)
        payload = urllib.parse.urlencode(fields).encode()
        request = urllib.request.Request(f"http://{box.host}/data.lua", data=payload)
        with self._opener(request, timeout=25) as response:
            body = json.loads(response.read().decode())
        if body.get("pid") != page:
            raise FritzError(f"{box.host} returned page {body.get('pid')!r} instead of {page!r}.")
        return body.get("data") or {}

    def api(self, box: Box, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            f"http://{box.host}{path}",
            data=data,
            method=method,
            headers={
                "AUTHORIZATION": f"AVM-SID {self.sid(box)}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=20) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            raise FritzError(f"{method} {path} failed ({error.code}): {detail}") from error
        if not raw:
            return {}
        return json.loads(raw)

    def mesh_status(self) -> dict:
        members = []
        for box in self.boxes:
            try:
                radio = radio_summary(self.data(box, "chan"))
                wlan = redact(self.api(box, "GET", "/api/v0/generic/wlan"))
                members.append(
                    {
                        "name": box.name,
                        "host": box.host,
                        "reachable": True,
                        "adopted": radio["adopted"],
                        "ssid": wlan.get("ssid"),
                        "ssid_5ghz": wlan.get("ssid_scnd"),
                        "channel": wlan.get("channel"),
                        "channel_5ghz": wlan.get("channel_scnd"),
                        "backhaul_steering": wlan.get("backhaul_steering"),
                        "band_steering": radio["band_steering"],
                        "channel_mode": radio["channel_mode"],
                        "power_step": radio["power_step"],
                    }
                )
            except (FritzError, OSError, json.JSONDecodeError, ET.ParseError) as error:
                members.append(
                    {"name": box.name, "host": box.host, "reachable": False, "error": str(error)}
                )
        return {"master": self.master.host, "members": members}

    def list_devices(self) -> list[dict]:
        devices = self.data(self.master, "homeNet").get("devices") or []
        compact = []
        for device in devices:
            conn = device.get("conninfo") or {}
            bands = conn.get("bandinfo") or []
            compact.append(
                {
                    "uid": device.get("UID"),
                    "name": (device.get("nameinfo") or {}).get("name"),
                    "ip": device.get("ipinfo"),
                    "connection": device.get("conn"),
                    "parent": device.get("parent"),
                    "band": conn.get("desc"),
                    "speed": conn.get("speed"),
                    "online": (device.get("stateinfo") or {}).get("online"),
                    "signal_dbm": (bands[0].get("rssi") if bands and isinstance(bands[0], dict) else None),
                }
            )
        return compact

    def get_device(self, uid: str) -> dict:
        data = self.data(self.master, "edit_device", {"dev": uid})
        device = ((data.get("vars") or {}).get("dev")) or {}
        ipv4 = device.get("ipv4") or {}
        wlan = ((device.get("wlan") or {}).get("devs") or [{}])[0]
        return redact(
            {
                "uid": device.get("UID") or uid,
                "name": (device.get("name") or {}).get("displayName"),
                "mac": device.get("mac"),
                "ip": (ipv4.get("current") or {}).get("ip"),
                "dhcp": (ipv4.get("current") or {}).get("dhcp") == "1",
                "reserved": bool((ipv4.get("dhcp") or {}).get("alwaysSameIp")),
                "band": wlan.get("band"),
                "signal_dbm": wlan.get("signalstrength"),
                "standard": wlan.get("wlanStandard"),
                "rate": wlan.get("curRate"),
                "state": device.get("state"),
            }
        )

    def get_radio(self, host: str | None = None) -> dict:
        box = self._box(host)
        summary = radio_summary(self.data(box, "chan"))
        summary["host"] = box.host
        return summary

    def update_radio(self, host: str | None = None, **changes: str) -> dict:
        if not changes:
            raise FritzError("No radio setting was requested.")
        allowed = {
            "bandsteering",
            "channelSelectMode",
            "autopowerlevel",
            "coexist",
            "use1213",
            "chan24ghz",
            "chan5ghz",
            "bandActive24ghz",
            "bandActive5ghz",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise FritzError(f"Refusing radio fields that are not explicit settings: {sorted(unknown)}.")
        box = self._box(host)
        if box is not self.master:
            raise FritzError("Radio writes go to the mesh master. Adopted repeaters take its settings.")
        before = self.data(box, "chan")
        fields = radio_form(before, **changes)
        self.data(box, "chan", fields)
        after = radio_summary(self.data(box, "chan"))
        after["host"] = box.host
        after["changed"] = sorted(changes)
        return after

    def set_backhaul_steering(self, enabled: bool) -> dict:
        value = "1" if enabled else "0"
        self.api(self.master, "PUT", "/api/v0/generic/wlan", {"backhaul_steering": value})
        current = self.api(self.master, "GET", "/api/v0/generic/wlan")
        return {
            "backhaul_steering": current.get("backhaul_steering") == "1",
            "ssid": current.get("ssid"),
        }

    def reserve_ipv4(self, uid: str, reserve: bool, ip: str | None = None) -> dict:
        body = {"static_dhcp": "1" if reserve else "0"}
        if ip:
            body["ip"] = ip
        self.api(self.master, "PUT", f"/api/v0/generic/landevice/landevice/{uid}", body)
        current = self.api(self.master, "GET", f"/api/v0/generic/landevice/landevice/{uid}")
        return {
            "uid": current.get("UID") or uid,
            "name": current.get("name"),
            "ip": current.get("ip"),
            "mac": current.get("mac"),
            "reserved": current.get("static_dhcp") == "1",
        }

    def tr064(self, host: str | None = None):
        from fritz_mesh_mcp import tr064

        box = self._box(host)
        cached = self._tr064.get(box.host)
        if cached is None:
            cached = tr064.connect(box)
            self._tr064[box.host] = cached
        return cached

    def _box(self, host: str | None) -> Box:
        if host is None:
            return self.master
        for box in self.boxes:
            if box.host == host or box.name == host:
                return box
        raise FritzError(f"No configured FRITZ!Box matches {host!r}.")


def boxes_from_env(environ: dict | None = None) -> list[Box]:
    env = environ if environ is not None else os.environ
    boxes = []
    specs = [
        ("master", "FRITZ_MASTER"),
        ("repeater-1", "FRITZ_REPEATER_1"),
        ("repeater-2", "FRITZ_REPEATER_2"),
    ]
    for name, prefix in specs:
        host = env.get(f"{prefix}_HOST", "").strip()
        user = env.get(f"{prefix}_USER", "").strip()
        password = env.get(f"{prefix}_PASSWORD", "")
        if host and user and password:
            boxes.append(Box(name, host, user, password))
    return boxes
