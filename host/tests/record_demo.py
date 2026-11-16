"""Records what the key's screen shows during real requests: hook -> daemon -> firmware simulator -> key presses.
Writes demo.gif next to the simulator screenshots."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

from PIL import Image, ImageDraw

HOST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIMDIR = os.path.join(os.path.dirname(HOST), "firmware", "sim")
FAKE = os.path.join(HOST, "tests", "fakeble")
AIR, CTL = 47950, 47951
home = tempfile.mkdtemp()
json.dump({"lanes": [f"127.0.0.1:{AIR}"]}, open(os.path.join(home, "config.json"), "w"))
ENV = dict(os.environ, NOD_HOME=home, PYTHONPATH=f"{FAKE}:{HOST}")
PY = sys.executable

sim = subprocess.Popen([os.path.join(SIMDIR, "nod_sim"), str(AIR), str(CTL)], stdout=subprocess.PIPE, text=True)
sim.stdout.readline()
daemon = subprocess.Popen([PY, "-m", "nod.cli", "daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV)


class Ctl:
    def __init__(self):
        self.lock = threading.Lock()
        self.s = socket.create_connection(("127.0.0.1", CTL))
        self.f = self.s.makefile("r")

    def __call__(self, cmd):
        with self.lock:
            self.s.sendall((cmd + "\n").encode())
            return self.f.readline().strip()


ctl = Ctl()
frames, caption = [], ["starting"]
frame_dir = tempfile.mkdtemp()
stop = False


def grab():
    i = 0
    while not stop:
        p = os.path.join(frame_dir, f"{i:04d}.ppm")
        ctl("snap " + p)
        frames.append((p, caption[0]))
        i += 1
        time.sleep(0.07)


def hook(cmd):
    p = subprocess.Popen([PY, "-m", "nod.cli", "hook", "claude"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, env=ENV)
    p.stdin.write(json.dumps({"hook_event_name": "PermissionRequest", "cwd": "/home/hardy/athens-sound",
                              "tool_name": "Bash", "tool_input": {"command": cmd}}))
    p.stdin.close()
    return p


def ready(timeout=6):
    t = time.time()
    while time.time() - t < timeout:
        live = [x for x in json.loads(ctl("tiles")) if x["state"] == 0]
        if live and live[0]["y"] >= 180:
            return True
        time.sleep(0.05)
    return False


def press(secs=0.06):
    ctl("key 1"); time.sleep(secs); ctl("key 0")


def result(p):
    out = p.communicate(timeout=10)[0]
    return json.loads(out)["hookSpecificOutput"]["decision"]["behavior"] if out.strip() else "no answer"


time.sleep(2.0)
threading.Thread(target=grab, daemon=True).start()
log = []

caption[0] = "Claude Code asks to run: npm run test"
h = hook("npm run test"); ready(); time.sleep(0.6)
caption[0] = "Tap"
press(); log.append(("npm run test, tap", result(h))); time.sleep(0.8)

caption[0] = "Claude Code asks: rm -rf build/ (risky)"
h = hook("rm -rf build/"); ready(); time.sleep(0.5)
caption[0] = "Tap: ignored on a risky tile"
press(); time.sleep(1.0)
caption[0] = "Hold 1.0 s"
press(1.3); log.append(("rm -rf build/, hold", result(h))); time.sleep(0.8)

caption[0] = "Claude Code asks: git push --force"
h = hook("git push --force origin main"); ready(); time.sleep(0.5)
caption[0] = "Double-tap: deny"
press(); time.sleep(0.12); press(); log.append(("git push --force, double-tap", result(h))); time.sleep(0.9)

caption[0] = "5 requests at once: 3 shown, +2 waiting"
hs = [hook(c) for c in ["npm run lint", "npm run build", "git status", "ls docs", "cat package.json"]]
time.sleep(2.2)
for _ in range(5):
    caption[0] = "Tap through the queue"
    ready(); press(); time.sleep(0.75)
log.append(("5 queued, 5 taps", ",".join(result(p) for p in hs)))
caption[0] = "All clear"
time.sleep(1.0)
stop = True
time.sleep(0.2)

S = 2
imgs = []
for p, cap in frames:
    try:
        im = Image.open(p).convert("RGB").resize((172 * S, 320 * S), Image.NEAREST)
    except Exception:
        continue
    canvas = Image.new("RGB", (172 * S + 40, 320 * S + 80), (233, 230, 223))
    canvas.paste(im, (20, 20))
    ImageDraw.Draw(canvas).text((20, 320 * S + 34), cap, fill=(22, 22, 26))
    imgs.append(canvas.quantize(colors=64))
out = os.path.join(SIMDIR, "shots", "demo.gif")
imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=70, loop=0, optimize=True)
for name, res in log:
    print(f"{name:32s} -> {res}")
print(f"{len(imgs)} frames -> {out}")
daemon.terminate(); ctl("quit"); sim.wait(5)
