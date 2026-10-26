import hashlib
import json
import unittest
import urllib.request
from xml.etree import ElementTree as ET

from fritz_mesh_mcp.client import Box, FritzClient, login_response, radio_form, redact


class LoginTests(unittest.TestCase):
    def test_pbkdf2_challenge(self):
        challenge = "2$1000$00112233445566778899aabbccddeeff"
        response = login_response(challenge, "secret")
        digest = hashlib.pbkdf2_hmac("sha256", b"secret", bytes.fromhex("00112233445566778899aabbccddeeff"), 1000)
        self.assertEqual(response, f"{challenge}${digest.hex()}")

    def test_two_round_pbkdf2(self):
        challenge = "2$1$aa$1$bb"
        first = hashlib.pbkdf2_hmac("sha256", b"secret", bytes.fromhex("aa"), 1)
        second = hashlib.pbkdf2_hmac("sha256", first, bytes.fromhex("bb"), 1)
        self.assertEqual(login_response(challenge, "secret"), f"bb${second.hex()}")

    def test_legacy_challenge(self):
        response = login_response("7cabc123", "secret")
        expected = hashlib.md5("7cabc123-secret".encode("utf-16le")).hexdigest()
        self.assertEqual(response, f"7cabc123-{expected}")


class RadioFormTests(unittest.TestCase):
    def snapshot(self):
        return {
            "channelSelectMode": "auto",
            "bandSteering": {"on": False, "disabled": False},
            "powerLevel": {"current": "", "options": [{"value": "1"}]},
            "auto1213": {"on": False},
            "coexist": {"on": False},
            "bands": ["24ghz", "5ghz"],
            "24ghz": {"active": True, "currentChannel": 0, "currentWlanMode": "", "useable": True, "channels": []},
            "5ghz": {"active": True, "currentChannel": 0, "currentWlanMode": "", "useable": True, "channels": []},
        }

    def test_steering_change_keeps_channel_mode_and_channels(self):
        form = radio_form(self.snapshot(), bandsteering="off")
        self.assertEqual(form["channelSelectMode"], "auto")
        self.assertEqual(form["chan24ghz"], "0")
        self.assertEqual(form["chan5ghz"], "0")
        self.assertEqual(form["bandsteering"], "off")
        self.assertNotIn("ssid", form)
        self.assertNotIn("autopowerlevel", form)

    def test_power_step_is_explicit(self):
        form = radio_form(self.snapshot(), autopowerlevel="1")
        self.assertEqual(form["autopowerlevel"], "1")
        self.assertEqual(form["channelSelectMode"], "auto")

    def test_redact_drops_wifi_secrets(self):
        self.assertNotIn("pskvalue", redact({"ssid": "home", "pskvalue": "secret"}))


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ClientTests(unittest.TestCase):
    def test_reserve_uses_the_device_api(self):
        calls = []

        def opener(request, timeout=8):
            if isinstance(request, urllib.request.Request):
                calls.append((request.get_method(), request.full_url, request.data))
                if "login_sid.lua" in request.full_url:
                    return _Response(b"<SessionInfo><SID>aaaaaaaaaaaaaaaa</SID></SessionInfo>")
                return _Response(b'{"UID":"landevice1","name":"Speaker","ip":"10.0.0.20","mac":"AA:BB:CC:DD:EE:FF","static_dhcp":"1"}')
            return _Response(b"<SessionInfo><SID>0000000000000000</SID><Challenge>abcdef12</Challenge></SessionInfo>")

        client = FritzClient([Box("master", "10.0.0.1", "user", "pw")], opener=opener)
        result = client.reserve_ipv4("landevice1", True)
        self.assertTrue(result["reserved"])
        method, url, data = calls[-2]
        self.assertEqual(method, "PUT")
        self.assertIn("/landevice/landevice1", url)
        self.assertEqual(json.loads(data), {"static_dhcp": "1"})


if __name__ == "__main__":
    unittest.main()
