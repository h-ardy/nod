"""nod demo: try Nod Dot with no key plugged in.

Starts the daemon with one simulated key, sends a few made-up requests one at a time,
and turns your keyboard into the key:

  space or t   tap         approve (a risky request needs a hold first)
  h            hold        open the request on the Nod Dot panel
  d            double-tap  deny
  q            quit

Nothing real runs. The requests are fake and only the daemon sees the answers.
"""
import asyncio
import os
import select
import sys
import termios
import threading
import time
import tty

from . import client

SCRIPT = [
    dict(source="claude-code", l1="Bash", l2="npm install", l3="nod/site",
         detail="npm install\n\nInstalls the packages listed in package.json.",
         why="Install dependencies before running the build"),
    dict(source="git", l1="git push", l2="main -> origin", l3="3 commits",
         detail="Pushing 3 commits to origin/main:\n  fix footer gap\n  add purpose text\n  wheel clip",
         why="Ship the website fixes"),
    dict(source="claude-code", l1="Bash", l2="rm -rf build/", l3="nod/desktop", risky=True,
         detail="rm -rf build/\n\nDeletes the build folder and everything in it.",
         why="Clear old build output before packaging"),
    dict(source="codex", l1="Edit", l2="src/auth.ts", l3="+14 -3",
         detail="Edits src/auth.ts:\n  adds a session timeout check\n  removes an unused import",
         why="Log users out after 30 minutes idle"),
    dict(source="claude-code", l1="WebFetch", l2="api.github.com", l3="read only",
         detail="GET https://api.github.com/repos/h-ardy/nod/releases",
         why="Look up the latest release tag"),
]

KEYS = {" ": "tap", "t": "tap", "h": "hold", "d": "double"}


def _start_daemon():
    from . import daemon
    threading.Thread(target=lambda: asyncio.run(daemon.main(sim=1)), daemon=True).start()
    for _ in range(50):
        try:
            client.status()
            return True
        except Exception:
            time.sleep(0.1)
    return False


def _say(msg):
    sys.stdout.write("\r\n" + msg + "\r\n")
    sys.stdout.flush()


def _feeder(stop):
    for i, req in enumerate(SCRIPT, 1):
        if stop.is_set():
            return
        tag = "  (risky: hold first)" if req.get("risky") else ""
        _say(f"request {i}/{len(SCRIPT)}: {req['l1']}  {req['l2']}{tag}")
        res = client.ask(**req, wait=300)
        _say(f"  -> {res.get('decision')}")
        time.sleep(1.2)
    _say("that's the whole demo. press q to quit, or run nod demo again.")


def main():
    if not sys.stdin.isatty():
        print("nod demo needs a terminal window")
        return 2
    try:
        client.status()
        print("a nod daemon is already running. stop it (Ctrl-C in its window) and run nod demo again.")
        return 2
    except Exception:
        pass
    if not _start_daemon():
        print("could not start the daemon")
        return 2
    print("\n\n".join(__doc__.split("\n\n")[1:3]))
    print("watch the dot in the corner of your screen.\n")
    stop = threading.Event()
    threading.Thread(target=_feeder, args=(stop,), daemon=True).start()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.2)
            if not r:
                continue
            ch = os.read(fd, 1).decode(errors="ignore").lower()
            if ch == "q":
                break
            kind = KEYS.get(ch)
            if kind:
                _say(f"[{kind}] {client.sim_press(0, kind).get('result')}")
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    print("\nbye")
    return 0
