# fritz-mesh-mcp

stdio MCP for a FRITZ!Box mesh. It logs in with the current two-round PBKDF2 challenge and also accepts the older single-round and MD5 challenges. Writes go to the mesh master. Adopted repeaters are read so you can see that they still follow it.

Other public Fritz MCPs stop at TR-064, telephony, or a generic “post this web form” call. TR-064 does not expose client band steering, transmit power, or the “always assign this IPv4 address” flag. A partial post of the channel page is what clears channel mode and power. This server names those settings and, on every radio change, resubmits the current channel mode, channels, and power with the one field you are changing.

## What the others do not name

| | This server | [dimitree2k/fritzbox-mcp](https://github.com/dimitree2k/fritzbox-mcp) | [ghbalf/mcp-fritzbox](https://github.com/ghbalf/mcp-fritzbox) | [kambriso/fritzbox-mcp-server](https://github.com/kambriso/fritzbox-mcp-server) | [the78mole/fritzmoles-mcp](https://github.com/the78mole/fritzmoles-mcp) |
|---|---|---|---|---|---|
| Several boxes, master plus adopted repeaters | yes | one box | one box | one box | telephony |
| Current PBKDF2 login | yes | yes | MD5 only | varies | TR-064 |
| Client band steering | named tool | only via a raw page post | no | no | no |
| Channel mode and transmit power, saved with the other radio fields | yes | raw page post | no | no | no |
| Mesh backhaul steering | yes | no | no | no | no |
| Per-device IPv4 reservation | yes, `/api/v0` | no (TR-064 cannot) | no | no | no |
| WAN, Wi-Fi list, DHCP range, log, port forwards, guest Wi-Fi, UPnP, Wake-on-LAN, smart home, reboot | named tools | named tools, plus a generic action caller | partial | home automation | calls and answering machine |

`dimitree2k/fritzbox-mcp` can reach settings this server does not wrap, because it will post any page and call any TR-064 action. That is a wider escape hatch, and it is the path that drops radio settings. This server does not include that escape hatch.

## Tools

Mesh and devices: `fritz_mesh_status`, `fritz_list_devices`, `fritz_get_device`.

Radio, master only: `fritz_get_radio`, `fritz_set_band_steering`, `fritz_set_channel_mode`, `fritz_set_transmit_power` (1 is 100%, then 50, 25, 12, and 6 percent), `fritz_set_coexistence`, `fritz_set_backhaul_steering`.

Addressing: `fritz_reserve_ipv4`, `fritz_lan_dhcp`.

Router: `fritz_connection_status`, `fritz_wifi_networks`, `fritz_system_log`, `fritz_port_forwards`, `fritz_set_guest_wifi`, `fritz_set_wan_access`, `fritz_set_upnp`, `fritz_wake_on_lan`, `fritz_smart_home_devices`, `fritz_set_smart_home_switch`, `fritz_reboot`.

Wi-Fi passwords are dropped from every reply.

## Run

```bash
uv sync
export FRITZ_MASTER_HOST=fritz.box
export FRITZ_MASTER_USER=...
export FRITZ_MASTER_PASSWORD=...
# optional adopted repeaters
export FRITZ_REPEATER_1_HOST=repeater-1.local
export FRITZ_REPEATER_1_USER=...
export FRITZ_REPEATER_1_PASSWORD=...
uv run fritz-mesh-mcp
```

Cursor, or any other stdio client:

```json
{
  "mcpServers": {
    "fritz-mesh": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/fritz-mesh-mcp", "fritz-mesh-mcp"]
    }
  }
}
```

The FRITZ!Box user needs the settings permission. TR-064 (port 49000) has to be reachable on the LAN. `fritz_reboot` takes the master offline for about two minutes.

## Tests

```bash
uv run python -m unittest tests.test_client
```

The unit tests do not touch a router. A live check is logging in and reading `fritz_get_radio` before any write.
