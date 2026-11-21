"""Tests the real Nod firmware running in the desktop simulator.

Covers both protocols (Nod daemon, Claude desktop Hardware Buddy), key gestures, two simultaneous
connections, and saves screenshots of every screen state to ./shots.
"""
import re, json
import os
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AIR, CTL = 47910, 47911
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


class Ctl:
    def __init__(self):
        self.s = socket.create_connection(("127.0.0.1", CTL))
        self.f = self.s.makefile("r")

    def __call__(self, cmd):
        self.s.sendall((cmd + "\n").encode())
        return self.f.readline().strip()

    def tiles(self):
        return json.loads(self("tiles"))

    def stat(self):
        return json.loads(self("stat"))

    def tap(self):
        self("key 1"); time.sleep(0.06); self("key 0")

    def double(self):
        self.tap(); time.sleep(0.12); self.tap()

    def hold(self, secs=1.3):
        self("key 1"); time.sleep(secs); self("key 0")

    def snap(self, name):
        ppm = os.path.join(SHOTS, name + ".ppm")
        self("snap " + ppm)
        try:
            from PIL import Image
            Image.open(ppm).save(os.path.join(SHOTS, name + ".png"))
            os.remove(ppm)
        except ImportError:
            pass


class Central:
    """A Bluetooth central as seen by the key: the Nod daemon or the Claude desktop app."""

    def __init__(self):
        self.s = socket.create_connection(("127.0.0.1", AIR))
        self.lines, self.buf = [], b""
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            try:
                d = self.s.recv(4096)
            except OSError:
                return
            if not d:
                return
            self.buf += d
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                self.lines.append(json.loads(line))

    def send(self, obj):
        self.s.sendall((json.dumps(obj) + "\n").encode())

    def expect(self, pred, timeout=2.0):
        t = time.time()
        while time.time() - t < timeout:
            for m in list(self.lines):
                if pred(m):
                    self.lines.remove(m)
                    return m
            time.sleep(0.02)
        return None

    def close(self):
        self.s.shutdown(socket.SHUT_RDWR)   # wakes the reader thread so the peer sees the disconnect
        self.s.close()


def wait_ready(ctl, timeout=4):
    t = time.time()
    while time.time() - t < timeout:
        live = [x for x in ctl.tiles() if x["state"] == 0]
        if live and live[0]["y"] >= 180:
            return live[0]
        time.sleep(0.05)
    return None


def wait_empty(ctl, timeout=2):
    t = time.time()
    while time.time() - t < timeout:
        if not ctl.tiles():
            return True
        time.sleep(0.05)
    return False


import tempfile, shutil
FS = tempfile.mkdtemp(prefix="nod_fs_")                 # the key's flash, fresh for this run
sim = subprocess.Popen([os.path.join(HERE, "nod_sim"), str(AIR), str(CTL)], stdout=subprocess.PIPE, text=True,
                       env=dict(os.environ, NOD_SIM_FS=FS))
print(sim.stdout.readline().strip())
ctl = Ctl()
check("advertises as Nod-XXXX by default (no Claude prefix)", re.fullmatch(r"Nod-[0-9A-F]{4}", ctl.stat()["name"]) is not None,
      ctl.stat()["name"])
ctl.snap("01_waiting")

# ------------------------------------------------------------ Nod daemon protocol
pc = Central()
pc.send({"t": "lane", "n": 2})
hello = pc.expect(lambda m: m.get("t") == "hello")
check("daemon link: key says hello with firmware version", hello and hello["fw"] == "0.2.1", str(hello))
check("lane number set", ctl.stat()["lane"] == 2)
ctl.snap("02_all_clear")

pc.send({"t": "add", "id": "a1", "src": "CLAUDE CODE", "c": "D97757", "l1": "Bash", "l2": "npm run test",
         "l3": "athens-sound", "risk": 0})
time.sleep(0.35)
ctl.snap("03_falling")
ctl.tap()                                           # pressed while still falling
time.sleep(0.5)
check("press while the tile is still falling is ignored", pc.expect(lambda m: m.get("t") == "ans", 0.3) is None)
check("tile reaches the line", wait_ready(ctl) is not None)
check("key light takes the source color", ctl("led") == "D97757", ctl("led"))
ctl.snap("04_ready")
ctl.tap()
time.sleep(0.4)
ctl.snap("05_approved_anim")
a = pc.expect(lambda m: m.get("t") == "ans")
check("tap approves (after the double-tap window)", a == {"t": "ans", "id": "a1", "d": "allow"}, str(a))
check("approved tile clears", wait_empty(ctl))

pc.send({"t": "add", "id": "a2", "src": "GIT PUSH", "c": "3FB950", "l1": "main to origin", "l2": "3 commits +142 -37",
         "l3": "athens-sound-co", "risk": 0})
wait_ready(ctl)
ctl.snap("06_git_ready")
ctl.double()
time.sleep(0.2)
ctl.snap("07_denied_anim")
a = pc.expect(lambda m: m.get("t") == "ans")
check("double-tap denies", a and a["d"] == "deny" and a["id"] == "a2", str(a))
wait_empty(ctl)

pc.send({"t": "add", "id": "a3", "src": "CODEX", "c": "E8E6E1", "l1": "Shell", "l2": "rm -rf dist/",
         "l3": "web  RISK: rm -r/-f", "risk": 1})
wait_ready(ctl)
check("risky tile lights the key red", ctl("led") == "F04438", ctl("led"))
ctl.tap()
time.sleep(0.6)
check("tap on a risky tile does nothing", pc.expect(lambda m: m.get("t") == "ans", 0.2) is None)
ctl.snap("08_risky_hint")
ctl("key 1"); time.sleep(0.6)
ctl.snap("09_risky_holding")
time.sleep(0.7); ctl("key 0")
a = pc.expect(lambda m: m.get("t") == "ans")
check("1.0 s hold approves the risky tile", a and a["d"] == "allow" and a["id"] == "a3", str(a))
wait_empty(ctl)

for i, (src, c, l1, l2) in enumerate([("CLAUDE CODE", "D97757", "Edit", "src/routes.ts"),
                                     ("CLAUDE CODE", "D97757", "Bash", "git commit -m wip"),
                                     ("CLAUDE CODE", "D97757", "Write", "docs/setup.md")]):
    pc.send({"t": "add", "id": f"q{i}", "src": src, "c": c, "l1": l1, "l2": l2, "l3": "athens-sound", "risk": 0})
wait_ready(ctl); time.sleep(0.6)
ctl.snap("10_queue_of_three")
ctl.tap(); time.sleep(0.45)
a = pc.expect(lambda m: m.get("t") == "ans")
check("queue answers oldest first", a and a["id"] == "q0", str(a))
pc.send({"t": "del", "id": "q1"})
time.sleep(0.2)
check("del withdraws a tile", [t["id"] for t in ctl.tiles() if t["state"] == 0] == ["q2"], str(ctl.tiles()))
pc.send({"t": "del", "id": "q2"})
wait_empty(ctl)

pc.send({"t": "note", "id": "n1", "src": "CLAUDE CODE", "c": "D97757", "l1": "Done", "l2": "Refactor finished"})
wait_ready(ctl)
ctl.snap("11_done_note")
ctl.tap(); time.sleep(0.45)
check("tap clears a note and acks it", pc.expect(lambda m: m == {"t": "ack", "id": "n1"}) is not None)
ctl.tap(); time.sleep(0.1)
check("press with nothing showing sends btn", pc.expect(lambda m: m.get("t") == "btn") is not None)
pc.send({"t": "pair"})
time.sleep(0.15)
ctl.snap("12_pair_press")
ctl.tap()
check("pairing press sends btn", pc.expect(lambda m: m.get("t") == "btn") is not None and not ctl.stat()["pairing"])

# ------------------------------------------------------------ Claude desktop Hardware Buddy protocol
app = Central()
app.send({"time": [1775731234, -18000]})
app.send({"cmd": "owner", "name": "Hardy"})
check("desktop: owner command acked", app.expect(lambda m: m.get("ack") == "owner") == {"ack": "owner", "ok": True, "n": 0})
app.send({"cmd": "status"})
st = app.expect(lambda m: m.get("ack") == "status")
check("desktop: status ack carries name, battery and stats",
      st and st["ok"] and st["data"]["name"].startswith("Nod-") and "appr" in st["data"]["stats"], str(st))
check("both computers connected at once", ctl.stat()["conns"] == 2)
check("advertising restarted so the second host could connect", ctl.stat()["adv_starts"] >= 2)

hb = {"total": 2, "running": 1, "waiting": 1, "msg": "approve: Bash", "entries": ["10:42 yarn test"],
      "tokens": 1200, "tokens_today": 300, "prompt": {"id": "req_abc123", "tool": "Bash", "hint": "yarn test"}}
app.send(hb)
t = wait_ready(ctl)
check("desktop prompt becomes a tile", t and t["src"] == "CLAUDE APP" and t["l1"] == "Bash" and t["proto"] == 2, str(t))
ctl.snap("13_desktop_prompt")
ctl.tap(); time.sleep(0.45)
d = app.expect(lambda m: m.get("cmd") == "permission")
check("tap sends the desktop decision 'once'", d == {"cmd": "permission", "id": "req_abc123", "decision": "once"}, str(d))
check("daemon link got nothing for the desktop prompt", pc.expect(lambda m: m.get("t") == "ans", 0.2) is None)
app.send(hb)                                         # the app has not caught up yet
time.sleep(0.4)
check("same prompt in a lagging heartbeat is not shown again",
      not [x for x in ctl.tiles() if x["id"] == "req_abc123" and x["state"] == 0], str(ctl.tiles()))
app.send({k: v for k, v in hb.items() if k != "prompt"})

app.send(dict(hb, prompt={"id": "req_2", "tool": "Bash", "hint": "rm -rf /tmp/build"}))
t = wait_ready(ctl)
check("desktop prompt with rm -rf is marked risky by the key", t and t["risky"], str(t))
ctl.double(); time.sleep(0.2)
d = app.expect(lambda m: m.get("cmd") == "permission")
check("double-tap sends 'deny' to the desktop", d and d["decision"] == "deny" and d["id"] == "req_2", str(d))
wait_empty(ctl)

app.send(dict(hb, prompt={"id": "req_3", "tool": "Edit", "hint": "src/app.ts"}))
wait_ready(ctl)
app.send({k: v for k, v in hb.items() if k != "prompt"} | {"waiting": 0})
time.sleep(0.3)
check("prompt answered in the app disappears from the key", not ctl.tiles(), str(ctl.tiles()))

app.send({"total": 1, "running": 1, "waiting": 0, "msg": "working", "entries": []})
time.sleep(0.1)
app.send({"total": 1, "running": 0, "waiting": 0, "msg": "idle", "entries": ["10:50 Drafted the venue emails"]})
t = wait_ready(ctl)
check("desktop session finishing shows a Done note", t and t["note"] and t["l2"].startswith("10:50"), str(t))
ctl.snap("14_desktop_done")
ctl.tap(); time.sleep(0.45)
check("clearing a desktop note sends nothing to the app", app.expect(lambda m: "cmd" in m, 0.2) is None and not ctl.tiles())

app.send({"cmd": "char_begin", "name": "bufo", "total": 1000})
check("folder push is declined (no ack)", app.expect(lambda m: m.get("ack") == "char_begin", 0.5) is None)
app.send({"cmd": "unpair"})
check("unpair clears bonds and acks", app.expect(lambda m: m.get("ack") == "unpair") is not None and ctl.stat()["bonds_cleared"] == 1)
app.send({"evt": "turn", "role": "assistant", "content": [{"type": "text", "text": "x" * 5000}]})
app.send(dict(hb, prompt={"id": "req_4", "tool": "Read", "hint": "README.md"}))
t = wait_ready(ctl)
check("an oversized turn event is dropped without breaking the next message", t and t["id"] == "req_4", str(t))

pc.send({"t": "add", "id": "mix1", "src": "GIT PUSH", "c": "3FB950", "l1": "main to origin", "l2": "1 commit", "l3": "", "risk": 0})
time.sleep(1.4)
ctl.snap("15_two_sources")
ctl.tap(); time.sleep(0.45)
d = app.expect(lambda m: m.get("cmd") == "permission")
check("with both sources queued, the oldest (desktop) is answered first", d and d["id"] == "req_4", str(d))
wait_ready(ctl)
ctl.tap(); time.sleep(0.45)
a = pc.expect(lambda m: m.get("t") == "ans")
check("then the daemon tile, answered on the daemon link", a and a["id"] == "mix1", str(a))

third = Central()
time.sleep(0.3)
check("a third connection is refused (radio holds two)", ctl.stat()["conns"] == 2)
third.close()

app.send(dict(hb, prompt={"id": "req_5", "tool": "Bash", "hint": "ls"}))
wait_ready(ctl)
app.close()
time.sleep(0.4)
check("desktop disconnect removes only its tiles", not ctl.tiles() and ctl.stat()["conns"] == 1, str(ctl.tiles()))

ctl("passkey 482913")
time.sleep(0.1)
ctl.snap("16_pair_code")
ctl("paired")
pc.close()
time.sleep(0.3)
check("daemon disconnect clears the lane number", ctl.stat()["lane"] == 0)
ctl("quit")
sim.wait(5)

# ------------------------------------------------------------ desktop-app name mode (hold key at power-up)
def boot(hold_ms, port):
    """Power the key up with the key held for hold_ms, return the advertised name."""
    p = subprocess.Popen([os.path.join(HERE, "nod_sim"), str(port), str(port + 1)], stdout=subprocess.PIPE,
                         text=True, env=dict(os.environ, NOD_SIM_FS=FS, NOD_SIM_HOLD_BOOT=str(hold_ms)))
    line = p.stdout.readline().strip()
    p.terminate(); p.wait(5)
    return line.split("name=")[-1]

n1 = boot(3600, 48110)
check("holding the key 3 s at power-up switches to desktop-app name Claude-Nod-XXXX", n1.startswith("Claude-Nod-"), n1)
n2 = boot(0, 48120)
check("desktop-app mode is remembered after a normal restart", n2 == n1, n2)
n3 = boot(1000, 48130)
check("letting go before 3 s changes nothing", n3 == n1, n3)
n4 = boot(3600, 48140)
check("holding again switches back to Nod-XXXX", n4.startswith("Nod-") and n4[4:] == n1[11:], n4)
shutil.rmtree(FS, ignore_errors=True)
print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
