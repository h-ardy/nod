"""Full chain with the real firmware in the simulator:
hooks / git / chat bridge -> nod daemon -> (fake) Bluetooth -> nod_key firmware -> key press -> back.
Also runs a fake Claude desktop app on one key at the same time as the daemon.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

HOST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM = os.path.join(os.path.dirname(HOST), "firmware", "sim", "nod_sim")
FAKE = os.path.join(HOST, "tests", "fakeble")
KEYS = [(47920, 47921), (47930, 47931)]
ENV = dict(os.environ, NOD_HOME=tempfile.mkdtemp(), PYTHONPATH=f"{FAKE}:{HOST}",
           NOD_FAKE_DEVICES=",".join((f"Claude-Nod-K{i}" if i == 0 else f"Nod-K{i}") + f"@127.0.0.1:{a}" for i, (a, _) in enumerate(KEYS)))
PY = sys.executable
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


class Ctl:
    def __init__(self, port):
        self.s = socket.create_connection(("127.0.0.1", port))
        self.f = self.s.makefile("r")

    def __call__(self, cmd):
        self.s.sendall((cmd + "\n").encode())
        return self.f.readline().strip()

    def tiles(self):
        return json.loads(self("tiles"))

    def tap(self):
        self("key 1"); time.sleep(0.06); self("key 0")

    def hold(self):
        self("key 1"); time.sleep(1.7); self("key 0")

    def ready(self, timeout=6):
        t = time.time()
        while time.time() - t < timeout:
            live = [x for x in self.tiles() if x["state"] == 0]
            if live and live[0]["y"] >= 180:
                return live[0]
            time.sleep(0.05)
        return None


def start_sim(air, ctl):
    p = subprocess.Popen([SIM, str(air), str(ctl)], stdout=subprocess.PIPE, text=True)
    p.stdout.readline()
    return p, Ctl(ctl)


def nod(*args, inp=None, bg=False, env=ENV):
    cmd = [PY, "-m", "nod.cli", *args]
    if bg:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    return subprocess.run(cmd, input=inp, capture_output=True, text=True, env=env)


def perm(cmd):
    return json.dumps({"hook_event_name": "PermissionRequest", "cwd": "/home/me/athens-sound",
                       "tool_name": "Bash", "tool_input": {"command": cmd}})


sims = [start_sim(a, c) for a, c in KEYS]
ctl = [c for _, c in sims]

# ------------------------------------------------------------ pairing: press the RIGHT key first
pair = nod("pair", bg=True)
for _ in range(100):                                  # wait until both keys show PRESS
    if all(json.loads(c("stat"))["pairing"] for c in ctl):
        break
    time.sleep(0.1)
ctl[1].tap(); time.sleep(0.3); ctl[0].tap()
out, err = pair.communicate(timeout=20)
cfg = json.load(open(os.path.join(ENV["NOD_HOME"], "config.json")))
check("nod pair saves lanes in press order", cfg["lanes"] == ["127.0.0.1:47930", "127.0.0.1:47920"], out + err)

# ------------------------------------------------------------ daemon over (fake) Bluetooth
daemon = subprocess.Popen([PY, "-m", "nod.cli", "daemon"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=ENV)
log = []
threading.Thread(target=lambda: [log.append(l) for l in daemon.stdout], daemon=True).start()
time.sleep(2.0)
st = json.loads(nod("status").stdout)
check("daemon connects to both keys", all(v["connected"] for v in st["lanes"].values()), str(st))
check("each key learned its lane number", json.loads(ctl[1]("stat"))["lane"] == 1 and json.loads(ctl[0]("stat"))["lane"] == 2)
check("daemon logs the keys' hello", any("firmware 0.2.0" in l for l in log), "".join(log))

h = nod("hook", "claude", bg=True); h.stdin.write(perm("npm run test")); h.stdin.close()
t = ctl[1].ready()
check("Claude Code request lands on lane 1 (the key pressed first)", t and t["l1"] == "Bash" and t["l2"] == "npm run test", str(t))
ctl[1].tap()
o = h.communicate(timeout=10)[0]
check("tap on the real firmware returns allow to Claude Code",
      json.loads(o)["hookSpecificOutput"]["decision"]["behavior"] == "allow", o)

h = nod("hook", "claude", bg=True); h.stdin.write(perm("rm -rf build/")); h.stdin.close()
t = ctl[1].ready()
check("risk flag survives the trip to the firmware", t and t["risky"], str(t))
ctl[1].tap(); time.sleep(0.6)
check("tap does not approve it", h.poll() is None)
ctl[1].hold()
o = h.communicate(timeout=10)[0]
check("hold approves it", json.loads(o)["hookSpecificOutput"]["decision"]["behavior"] == "allow", o)

h = nod("hook", "claude", bg=True); h.stdin.write(perm("make deploy")); h.stdin.close()
ctl[1].ready()
ctl[1]("key 1"); time.sleep(0.06); ctl[1]("key 0"); time.sleep(0.12); ctl[1]("key 1"); time.sleep(0.06); ctl[1]("key 0")
o = h.communicate(timeout=10)[0]
check("double-tap denies", json.loads(o)["hookSpecificOutput"]["decision"]["behavior"] == "deny", o)

# withdrawn: hook killed, tile leaves the key
h = nod("hook", "claude", bg=True); h.stdin.write(perm("ls")); h.stdin.close()
ctl[1].ready(); h.kill(); h.wait(); time.sleep(0.8)
check("killed hook removes the tile from the physical key", not ctl[1].tiles(), str(ctl[1].tiles()))

# git push routes to its lane, falls back to the least busy key when lane 3 does not exist
h = nod("ask", "--source", "git", "--l1", "main to origin", "--l2", "3 commits +142 -37", bg=True)
found = None
for _ in range(60):
    for i, c in enumerate(ctl):
        if c.tiles():
            found = i
    if found is not None:
        break
    time.sleep(0.1)
check("git request with no lane 3 goes to a free key", found is not None)
ctl[found].ready(); ctl[found].tap()
check("nod ask exits 0 on approve", h.wait(10) == 0)

# key reboots while a request is waiting: the daemon reconnects and puts the tile back
h = nod("hook", "claude", bg=True); h.stdin.write(perm("yarn build")); h.stdin.close()
ctl[1].ready()
sims[1][0].kill(); sims[1][0].wait()
time.sleep(0.5)
sims[1] = start_sim(*KEYS[1]); ctl[1] = sims[1][1]
t = ctl[1].ready(timeout=12)
check("after the key restarts, the pending tile comes back", t and t["l2"] == "yarn build", str(t))
ctl[1].tap()
o = h.communicate(timeout=10)[0]
check("and can still be approved", json.loads(o)["hookSpecificOutput"]["decision"]["behavior"] == "allow", o)

# ------------------------------------------------------------ overflow: 10 requests at once on one key
asks = [nod("ask", "--source", "claude-code", "--l1", "Bash", "--l2", f"job {i}", bg=True) for i in range(10)]
time.sleep(0.15 * 10)
for _ in range(60):
    if len([x for x in ctl[1].tiles() if x["state"] == 0]) >= 3 and json.loads(ctl[1]("stat"))["more"] == 7:
        break
    time.sleep(0.1)
live = [x for x in ctl[1].tiles() if x["state"] == 0]
check("key shows the 3 tiles that fit and the daemon holds the other 7", len(live) == 3, str(len(live)))
check("key shows +7 MORE", json.loads(ctl[1]("stat"))["more"] == 7, ctl[1]("stat"))
st = json.loads(nod("status").stdout)
check("daemon reports 7 parked requests", sum(1 for p in st["pending"] if not p["shown"]) == 7)
time.sleep(1.5)
ctl[1]("snap " + os.path.join(os.path.dirname(SIM), "shots", "17_plus_more.ppm"))
asks[9].kill(); asks[9].wait(); time.sleep(0.6)
check("a parked request whose caller quits just drops off the count", json.loads(ctl[1]("stat"))["more"] == 6, ctl[1]("stat"))
ctl[1].ready(); ctl[1].tap(); time.sleep(0.9)
live = [x for x in ctl[1].tiles() if x["state"] == 0]
check("answering one pulls the next parked request onto the key", len(live) == 3 and json.loads(ctl[1]("stat"))["more"] == 5,
      f"{len(live)} {ctl[1]('stat')}")
for _ in range(20):
    if not [x for x in ctl[1].tiles() if x["state"] == 0]:
        break
    ctl[1].ready(); ctl[1].tap(); time.sleep(0.5)
codes = [a.wait(20) for a in asks[:9]]
check("all 9 remaining requests were approved in order", codes == [0] * 9, str(codes))
check("counter cleared", json.loads(ctl[1]("stat"))["more"] == 0)

# ------------------------------------------------------------ Claude desktop app on lane 2 at the same time
app = socket.create_connection(("127.0.0.1", KEYS[0][0]))
app.sendall(b'{"cmd":"owner","name":"Hardy"}\n')
app.sendall((json.dumps({"total": 1, "running": 0, "waiting": 1, "msg": "approve: Write",
                         "entries": [], "prompt": {"id": "req_9", "tool": "Write", "hint": "notes.md"}}) + "\n").encode())
t = ctl[0].ready()
check("desktop-app prompt shows on the same key the daemon uses", t and t["src"] == "CLAUDE APP", str(t))
ctl[0].tap(); time.sleep(0.5)
app.settimeout(2)
got = b""
try:
    while b'"permission"' not in got:
        got += app.recv(4096)
except socket.timeout:
    pass
check("desktop app receives its decision", b'"decision":"once"' in got and b'req_9' in got, got.decode(errors="replace"))
check("daemon link still up on that key", json.loads(nod("status").stdout)["lanes"]["1"]["connected"])
app.shutdown(socket.SHUT_RDWR); app.close()

daemon.terminate()
daemon.wait(5)
for p, c in sims:
    try:
        c("quit")
    except OSError:
        pass
    try:
        p.wait(3)
    except subprocess.TimeoutExpired:
        p.kill()
print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
