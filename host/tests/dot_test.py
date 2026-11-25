"""Nod Dot flow with a simulated key: live events, hold to look, the panel opens, a tap approves.

Also checks that the events socket needs the token and can never answer a request itself.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time

import aiohttp

HOST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = tempfile.mkdtemp()
ENV = dict(os.environ, NOD_HOME=HOME, PYTHONPATH=HOST)
PY = sys.executable
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def nod(*args, inp=None, bg=False):
    cmd = [PY, "-m", "nod.cli", *args]
    if bg:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=ENV)
    return subprocess.run(cmd, input=inp, capture_output=True, text=True, env=ENV)


def press(kind):
    out = nod("press", "0", kind).stdout
    return json.loads(out.replace("'", '"'))["result"]


def perm(cmd, why=""):
    return json.dumps({"session_id": "s", "hook_event_name": "PermissionRequest", "cwd": "/home/me/site",
                       "tool_name": "Bash", "tool_input": {"command": cmd, "description": why}})


async def next_event(ws, ev, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        try:
            m = await asyncio.wait_for(ws.receive_json(), timeout=end - time.time())
        except asyncio.TimeoutError:
            return None
        if m.get("ev") == ev:
            return m
    return None


async def main():
    daemon = subprocess.Popen([PY, "-m", "nod.cli", "daemon", "--sim", "1"], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, env=ENV)
    assert "nod daemon" in daemon.stdout.readline()
    port = 47823
    token = open(os.path.join(HOME, "token")).read().strip()
    url = f"http://127.0.0.1:{port}/v1/events"
    try:
        async with aiohttp.ClientSession() as s:
            try:
                async with s.ws_connect(url + "?token=wrong"):
                    ok = False
            except aiohttp.WSServerHandshakeError as e:
                ok = e.status == 401
            check("events socket refuses a wrong token", ok)

            async with s.ws_connect(f"{url}?token={token}") as ws:
                hello = await next_event(ws, "hello")
                check("events socket says hello with what is pending", hello is not None and hello["pending"] == [], str(hello))

                cmd = "rm -rf build/ && git push --force origin main"
                h = nod("hook", "claude", bg=True)
                h.stdin.write(perm(cmd, "Clean the build folder and push the fix")); h.stdin.close()
                add = await next_event(ws, "add")
                req = add and add["req"]
                check("new request arrives with the full command", req and f"$ {cmd}" in req["detail"], str(req))
                check("and Claude's own reason, kept separate", req and req["why"] == "Clean the build folder and push the fix")
                check("and a 3-letter code made of easy-to-read letters",
                      req and len(req["code"]) == 3 and all(c in "ACDEFHJKMNPRTVWXY347" for c in req["code"]), str(req and req["code"]))
                check("and it is flagged risky", req and req["risky"])

                await ws.send_json({"cmd": "allow", "id": req["id"]})
                await ws.send_json({"decision": "allow", "id": req["id"]})
                await asyncio.sleep(0.4)
                check("the panel app cannot approve anything itself", h.poll() is None)

                r = await asyncio.to_thread(press, "hold")
                look = await next_event(ws, "look")
                check("holding the key opens the request on screen", r == "look" and look and look["req"]["id"] == req["id"], str(look))
                check("the code on screen matches the request", look and look["req"]["code"] == req["code"])

                await ws.send_json({"cmd": "opened", "id": req["id"]})
                await asyncio.sleep(0.3)
                r = await asyncio.to_thread(press, "tap")
                done = await next_event(ws, "done")
                out = json.loads(h.communicate(timeout=10)[0])
                check("with the panel open, a tap approves", r == "allow" and out["hookSpecificOutput"]["decision"]["behavior"] == "allow", r)
                check("the panel hears it was approved", done and done["id"] == req["id"] and done["decision"] == "allow", str(done))

                h = nod("hook", "claude", bg=True); h.stdin.write(perm("npm run lint")); h.stdin.close()
                add = await next_event(ws, "add")
                r = await asyncio.to_thread(press, "hold")
                await next_event(ws, "look")
                await ws.send_json({"cmd": "opened", "id": add["req"]["id"]})
                await ws.send_json({"cmd": "closed", "id": add["req"]["id"]})
                await asyncio.sleep(0.3)
                r = await asyncio.to_thread(press, "double")
                out = json.loads(h.communicate(timeout=10)[0])
                check("closing the panel and double-tapping denies", out["hookSpecificOutput"]["decision"]["behavior"] == "deny", r)

            # app closed: a hold now gets "no screen", and a second hold runs it
            h = nod("hook", "claude", bg=True); h.stdin.write(perm("rm -rf dist/")); h.stdin.close()
            time.sleep(0.8)
            r1 = await asyncio.to_thread(press, "hold")
            await asyncio.sleep(0.3)
            r2 = await asyncio.to_thread(press, "hold")
            out = json.loads(h.communicate(timeout=10)[0])
            check("with the app closed, hold then hold again runs it", r1 == "look" and r2 == "allow"
                  and out["hookSpecificOutput"]["decision"]["behavior"] == "allow", f"{r1} {r2}")
    finally:
        daemon.terminate()
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
