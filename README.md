# Nod: build and software guide

Try the working demo: https://h-ardy.github.io/nod/ (click the key, or press Space)

Nod is a 1 x 1 x 3 in key with a screen. Your AI agents and `git push` send approval requests to it over Bluetooth. Requests fall down the screen like piano tiles; the key under a lane answers the tile sitting on the line. You can start a long Claude Code run, walk away, and approve from the key when it lights up.

```
Claude Code CLI ──PermissionRequest hook──┐
git push ─────────pre-push hook───────────┤
other MCP chat apps ─nod MCP server───────┼──> nod daemon (laptop) ──Bluetooth──┐
anything else ────`nod ask` CLI───────────┘    127.0.0.1, token required        ├──> key 1, key 2, key 3 ...
Claude desktop app (Code Desktop, Cowork) ── Hardware Buddy Bluetooth bridge ───┘
```

Each key holds two Bluetooth connections at once: the nod daemon and the Claude desktop app. It works out which protocol each one speaks from its first message.

### What already exists
People have built approval buttons before, so here is where Nod sits:
- Anthropic's own [claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy) publishes the Bluetooth protocol the Claude desktop app uses for maker hardware (developer mode only, not an officially supported feature). Nod's firmware speaks it, so a key works with the desktop app with no daemon at all.
- [Claude Board](https://pypi.org/project/claude-board/) approves from a phone with hardware planned; [Gavel](https://github.com/etalli/Gavel) uses three buttons that type the answer as a USB keyboard; several M5Stack consoles exist on Hackster; OpenAI's Codex Micro macro pad was reported in July 2026.
- What Nod adds: a 1 x 1 x 3 in key with its own screen, magnetic stacking where each key is a lane, a queue that falls like piano tiles, per-source colors, git push approvals, hold-to-approve for risky commands, and one key serving the desktop app and the CLI at the same time.

## 1. Parts (one module)

| Part | Link | Price seen |
|---|---|---|
| Seeed Studio XIAO nRF52840 | https://www.seeedstudio.com/Seeed-XIAO-BLE-nRF52840-p-5201.html | $9.99 |
| Waveshare 1.47in LCD Module, 172x320, ST7789 | https://www.waveshare.com/1.47inch-lcd-module.htm | $9.99 |
| Kailh Choc v1 switches, 10-pack (red linear) | https://www.adafruit.com/product/5113 | $11.95 |
| LiPo 3.7 V 350 mAh, 36 x 19.6 x 5.2 mm, JST-PH | https://www.adafruit.com/product/2750 | $6.95 |
| Magnetic connector, right angle, 4 pins (one male + one female) | https://www.adafruit.com/product/5358 | $6.50 |
| 4x disc magnets 1/4 x 1/16 in N52 | https://www.kjmagnetics.com/d41-n52-neodymium-disc-magnet | $0.32 each |
| Optional key light: NeoPixel Nano 2020, 10-pack | https://www.adafruit.com/product/4684 | $3.95 |
| 1x M2 x 6 mm self-tapping screw, thin silicone wire (30 AWG), double-sided foam tape, CA glue | any hardware store | |

Rough total for one module: about $40 in parts, plus filament. Switches, magnets and LEDs come in packs, so each extra module is cheaper.

## 2. Print (ready-to-print files in `cad/print/`)

| File | Material | Orientation | Notes |
|---|---|---|---|
| `nod_shell.stl` | PETG or PLA, 0.2 mm layers, 3 walls, 20% infill | Already saved in print orientation: front (screen) face flat on the bed, open back facing up. Load it and don't rotate it. | Use a 5 mm brim. No supports needed: one 0.2 mm layer is bridged across the switch hole so the switch plate has something to print on. After printing, cut that thin layer out of the square hole with a hobby knife, running the blade along the hole's edges. |
| `nod_lid.stl` | same | Flat, inside face up | No supports. |
| `nod_keycap_fdm_leg1.20 / 1.28 / 1.35.stl` | PLA or PETG | Face down (already saved that way), no supports | Flat top (no finger dish) so the whole face sits on the bed. Printed in PLA, all three leg sizes fit the switch. Use at least 5 top layers so the inside of the cap prints solid. |
| `nod_keycap_resin_leg1.20 / 1.28.stl` | Resin | Face down | Resin prints true to size, so these use the drawing's own leg sizes. |

All parts check out with no clashes against the catalog sizes of the screen, switch, battery, XIAO and connectors (`cad/check_fit.py`). Two sizes were not published and are assumptions, so print the shell once and test fit before printing a stack:
- The Waveshare module's thickness and where its glass sits on the board. The window (`WIN_DY` in `nod_case.py`) assumes the glass is centred.
- The Adafruit 5358 body, taken as 21 x 7 x 7 mm from a reseller listing.

Every dimension is a named parameter at the top of `cad/nod_case.py`. Run `python3 nod_case.py` (needs `pip install cadquery trimesh`) to regenerate the STL and STEP files.

## 3. Wire

| XIAO pin | Goes to |
|---|---|
| D8 (SCK) | screen CLK |
| D10 (MOSI) | screen DIN |
| D1 | screen CS |
| D2 | screen DC |
| D3 | screen RST |
| D6 | screen BL |
| 3V3, GND | screen VCC, GND |
| D0 | one key switch pin; the other pin to GND |
| D7 | NeoPixel DIN (optional), its VDD to 3V3, GND to GND |
| BAT+ / BAT- pads on the back | battery red / black (cut the JST plug off, insulate well) |

The side connectors are not wired in v1. They line the modules up and are there for shared charging later. Charge each module with its own USB-C cable for now: tying several USB VBUS lines together needs proper power-path parts, so it's left out of v1.

## 4. Assemble

1. Glue the four magnets into the side pockets. Right side: N facing out at the top, S at the bottom. Left side: S at the top, N at the bottom. Check with a second module before the glue sets.
2. Push the male magnetic connector (pogo pins) into the right-side slot from the back, female into the left. Glue. Faces flush with the outside.
3. Clip the switch into the plate from the front, stem slots running left to right. Push the keycap on.
4. Screen in from the back, glass against the window, held by the two stop tabs and a strip of foam tape.
5. Battery behind the screen on foam tape. XIAO on the lid rails, USB-C lined up with the bottom opening.
6. Hook the lid's bottom edge under the bottom wall, lower it, one M2 screw at the top.

## 5. Firmware

Arduino IDE: add the Seeed board package, pick **Seeed nRF52 Boards > Seeed XIAO nRF52840** (not the "mbed" one). Install the libraries Adafruit GFX, Adafruit ST7735 and ST7789, ArduinoJson (v7) and Adafruit NeoPixel. Open `firmware/nod_key/` and upload. The code lives in `nod_key.cpp`.

A prebuilt package is included: `adafruit-nrfutil dfu serial -pkg firmware/nod_key_xiao_nrf52840_dfu.zip -p <port> -b 115200 --singlebank` (built with GCC 13 rather than the board package's own compiler; the IDE route above is the safer first flash).

Screen mirror (firmware 0.2.1 and newer): plug the key into your computer by USB, open `docs/mirror.html` in Chrome or Edge (or the Screen mirror page on the Nod site) and click Connect. It shows the key's screen live, including the pairing code, so you can test and pair a key before its screen is wired. The key only sends frames while that page has the port open. Turn it off with `#define NOD_MIRROR 0`.

Charging: plug USB-C into the XIAO. The firmware sets its charger to 100 mA (the board default is 50 mA), so a 400 mAh battery fills in about 4 to 5 hours. The case fits batteries up to 20 x 36 x 7.5 mm.

Builds for that board here: 189 KB of flash, 25 KB of static RAM, plus a 110 KB frame buffer allocated at boot. It has not run on a physical board yet. The same source, unchanged, runs in the desktop simulator (section 7), where 42 checks pass.

Key behaviour:
- A tile counts only once it has landed on the dashed line, so a stray press never answers something you haven't read.
- Tap approves. Double-tap denies.
- Risky tiles (red outline) ignore taps. Hold for 1.0 s to approve them.
- Info notes ("Done", "Waiting for you"): tap to clear.
- The screen fits 3 tiles. Extra requests wait on your computer, not the key, and the key shows "+N MORE" at the top. Each time you answer one, the next slides in. Nothing is dropped, however many sessions are asking.
- The screen goes dark after 30 s with nothing pending. Bluetooth stays connected.
- The key advertises as `Nod-XXXX` and works with any agent through the daemon. The Claude desktop app's device picker only lists names starting with "Claude", so for that app switch on desktop-app mode: hold the key while the board powers up (plug in USB or press reset) until the screen says DESKTOP APP MODE ON, about 3 s. The key then advertises as `Claude-Nod-XXXX`. Do the same again to switch back. The setting survives restarts.

Security: by default (`NOD_SECURE 1`) the key requires Bluetooth LE Secure Connections bonding, as Anthropic's protocol notes recommend, since command text travels over the radio. The first time a computer connects, the key shows a 6-digit code and your OS asks you to type it. macOS and Windows prompt automatically; on Linux, pair once with `bluetoothctl` first. Set `NOD_SECURE 0` at the top of `nod_key.cpp` to skip bonding while prototyping.

### Using a key with the Claude desktop app (Claude Code Desktop, Cowork)
1. In Claude for macOS or Windows: Help > Troubleshooting > Enable Developer Mode.
2. Turn on desktop-app mode on the key (hold it while powering up, see above).
3. Developer > Open Hardware Buddy..., click Connect, pick `Claude-Nod-XXXX`, type the code the key shows.
4. Permission prompts from desktop sessions now fall onto that key as "CLAUDE APP" tiles. A tap sends `once`, a double-tap sends `deny`. When a session stops running, a "Done" note appears.

This is enforced by the app itself, unlike the MCP chat bridge below. Per Anthropic, this Bluetooth API is for makers and developers in developer mode and isn't an officially supported product feature.

## 6. Laptop side

```
cd host && pip install .
nod pair                      # every key shows PRESS; press them left to right (stop the daemon first)
nod daemon                    # keep running (login item, launchd or systemd)
```

### Claude Code
`nod claude-settings` prints this. Merge it into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PermissionRequest": [{"hooks": [{"type": "command", "command": "nod hook claude", "timeout": 600}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "nod hook claude", "timeout": 10}]}],
    "Notification": [{"matcher": "idle_prompt", "hooks": [{"type": "command", "command": "nod hook claude", "timeout": 10}]}]
  }
}
```

- **PermissionRequest** fires only when Claude Code would otherwise show you its permission dialog. The hook waits for the key and answers allow or deny. If the key is off, times out (9 min) or the daemon isn't running, the hook prints nothing and you get the normal dialog. Nothing is ever approved by default.
- **Stop** puts a "Done" note on the key when a turn finishes, so you know to come back.
- **Notification / idle_prompt** puts "Waiting for you" on the key.

### git push
```
nod install-git /path/to/repo           # or set core.hooksPath for every repo
```
Each push waits on the git lane with branch, commit count and +/- lines. Force pushes and branch deletes need the hold. If the key is unavailable, the push goes through and prints a note. Set `NOD_GIT_STRICT=1` to block instead.

### Other chat apps (MCP clients)
For the Claude desktop app, use the Bluetooth route in section 5; it is enforced by the app. For other chat apps that support MCP servers, the bridge below is cooperative: chat apps don't have a hook that sees every action. The `nod` MCP server gives the model three tools: `request_approval`, `check_approval` and `notify_done`. Its instructions tell the model to call `request_approval` before anything with side effects and to stop on DENIED. It works because the model follows those instructions, not because the app enforces them. Keep the app's own confirmations for anything that really matters.

Example config (Claude Desktop format, `claude_desktop_config.json`; other apps use a similar block):
```json
{ "mcpServers": { "nod": { "command": "nod", "args": ["mcp"], "env": { "NOD_SOURCE": "chat" } } } }
```
Set the nod tools to "always allow" in the app so the key is the only place you answer. Long waits are split into 45 s calls (PENDING then `check_approval`), because chat apps time out long tool calls. A web-only chat (claude.ai in a browser) can't reach a server on your laptop without exposing it to the internet, so v1 doesn't support it.

### Anything else
`nod ask --source codex --l1 "Shell" --l2 "pytest -q"` exits 0 on approve, 1 on deny, 2 if unavailable. `nod notify --l1 Done --l2 "export finished"` shows a note. Point any tool that has a pre-action hook at these.

## 7. Test without hardware

Three test suites, 89 checks, all passing:

```
cd firmware/sim && ./build.sh && python3 firmware_test.py   # 38: the real firmware, both protocols, gestures, screenshots in shots/
cd host && python3 tests/e2e_test.py                        # 22: hooks, git, chat bridge against simulated keys
cd host && python3 tests/chain_test.py                      # 25: daemon -> firmware simulator over a fake Bluetooth link, incl. 10 requests at once
```

`firmware/sim` compiles `nod_key.cpp` unchanged for your computer, with stand-ins for the board, radio and screen and the real graphics and JSON libraries. Each TCP client is one Bluetooth connection, sent in 20-byte packets like a real default link, and every screen state is saved as a PNG. `host/tests/fakeble` swaps in for the `bleak` Bluetooth library so the real daemon talks to the simulator.

What these tests can't cover: the radio itself, pairing on a real OS, the screen's wiring, and a live Claude Code session. The Claude Code CLI couldn't sign in from the machine these were run on, so do one real run once you're set up: run `nod daemon --sim 1`, add the hooks block, ask Claude to run a command, then `nod press 0 tap`.

## 8. Safety rules built in
- Tile text is built from the real command, path or URL, never from the model's description of it.
- Risky patterns (rm -rf, sudo, force push, curl piped to a shell, chmod 777, dd, publish, DROP TABLE, terraform destroy, and in chats delete, buy, pay, transfer) need the 1.0 s hold.
- A timeout or a dead link never approves.
- The daemon listens only on 127.0.0.1 and wants a random token from `~/.nod/token`, so a web page can't send approvals to it.
- If a hook process is killed (you answered in the terminal instead), its tile comes off the key.
