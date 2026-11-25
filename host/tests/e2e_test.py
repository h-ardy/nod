"""End-to-end test with simulated keys: Claude Code hook, git pre-push, chat bridge (MCP)."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time

HOST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, NOD_HOME=tempfile.mkdtemp(), PYTHONPATH=HOST)
PY = sys.executable
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def nod(*args, inp=None, bg=False, cwd=None):
    cmd = [PY, "-m", "nod.cli", *args]
    if bg:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=ENV, cwd=cwd)
    return subprocess.run(cmd, input=inp, capture_output=True, text=True, env=ENV, cwd=cwd)


def status():
    return json.loads(nod("status").stdout)


def wait_pending(n=1, timeout=10):
    t = time.time()
    while time.time() - t < timeout:
        if len(status()["pending"]) >= n:
            return status()["pending"]
        time.sleep(0.1)
    return status()["pending"]


def press(lane, kind="tap"):
    return json.loads(nod("press", str(lane), kind).stdout.replace("'", '"'))["result"]


def perm(cmd, cwd="/home/me/athens-sound"):
    return json.dumps({"session_id": "s", "hook_event_name": "PermissionRequest", "cwd": cwd,
                       "tool_name": "Bash", "tool_input": {"command": cmd}})


# ---------------------------------------------------------------- start
check("hook with daemon down prints nothing (Claude shows its own dialog)",
      nod("hook", "claude", inp=perm("ls")).stdout.strip() == "")

daemon = subprocess.Popen([PY, "-m", "nod.cli", "daemon", "--sim", "4"], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, env=ENV)
assert "nod daemon" in daemon.stdout.readline()

# ---------------------------------------------------------------- Claude Code
h = nod("hook", "claude", bg=True); h.stdin.write(perm("npm run test")); h.stdin.close()
p = wait_pending()
check("PermissionRequest lands on lane 1 (Claude route)", p and p[0]["lane"] == 0 and p[0]["l1"] == "Bash" and not p[0]["risky"], str(p))
check("tap approves", press(0, "tap") == "allow")
out = json.loads(h.communicate(timeout=10)[0])
check("hook returns Claude Code allow JSON",
      out == {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}, json.dumps(out))

h = nod("hook", "claude", bg=True); h.stdin.write(perm("git commit -m wip")); h.stdin.close()
wait_pending(); press(0, "double")
out = json.loads(h.communicate(timeout=10)[0])
check("double-tap denies with a message", out["hookSpecificOutput"]["decision"]["behavior"] == "deny")

h = nod("hook", "claude", bg=True); h.stdin.write(perm("rm -rf build/")); h.stdin.close()
wait_pending()
r1 = press(0, "tap")
out = json.loads(h.communicate(timeout=10)[0])
check("risky tile takes a plain tap like any other", r1 == "allow" and out["hookSpecificOutput"]["decision"]["behavior"] == "allow", r1)

h = nod("hook", "claude", bg=True); h.stdin.write(perm("rm -rf build/")); h.stdin.close()
wait_pending()
r2 = press(0, "hold")
time.sleep(0.3)
check("hold asks to show it on screen; with no Nod Dot app open nothing runs yet", r2 == "look" and h.poll() is None, r2)
press(0, "hold")
out = json.loads(h.communicate(timeout=10)[0])
check("with no Nod Dot app, a second hold approves the risky one", out["hookSpecificOutput"]["decision"]["behavior"] == "allow")

h = nod("hook", "claude", bg=True); h.stdin.write(perm("make deploy")); h.stdin.close()
wait_pending(); h.kill(); h.wait()
time.sleep(0.8)
check("killed hook withdraws its tile from the key", status()["pending"] == [], str(status()["pending"]))

nod("hook", "claude", inp=json.dumps({"hook_event_name": "Stop", "cwd": "/x/athens-sound",
                                       "last_assistant_message": "Refactor finished, 14 tests pass."}))
p = wait_pending()
check("Stop hook puts a Done note on the key", p and p[0]["l1"] == "Done", str(p))
check("tap clears the note", press(0) == "note cleared" and status()["pending"] == [])

# ---------------------------------------------------------------- git
tmp = tempfile.mkdtemp()
remote, repo = os.path.join(tmp, "remote.git"), os.path.join(tmp, "athens-sound-co")
g = lambda *a, cwd=repo: subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=ENV)
subprocess.run(["git", "init", "-q", "--bare", remote])
subprocess.run(["git", "init", "-q", "-b", "main", repo])
g("config", "user.email", "t@t"); g("config", "user.name", "t")
g("remote", "add", "origin", remote)
for i in range(3):
    open(os.path.join(repo, f"f{i}.txt"), "w").write("x\n" * (i + 1)); g("add", "."); g("commit", "-qm", f"c{i}")
nod("install-git", repo)
push = subprocess.Popen(["git", "push", "-q", "origin", "main"], cwd=repo, env=ENV,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
p = wait_pending()
check("git push waits on lane 3 (git route)", p and p[0]["lane"] == 2 and p[0]["l1"] == "main to origin", str(p))
press(2)
check("tap lets the push through", push.wait(15) == 0 and g("ls-remote", remote).stdout != "")

open(os.path.join(repo, "f9.txt"), "w").write("y\n"); g("add", "."); g("commit", "-qm", "c9")
push = subprocess.Popen(["git", "push", "-q", "origin", "main"], cwd=repo, env=ENV,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
wait_pending(); press(2, "double")
check("double-tap blocks the push", push.wait(15) != 0)

g("reset", "-q", "--hard", "HEAD~2"); open(os.path.join(repo, "z.txt"), "w").write("z\n"); g("add", "."); g("commit", "-qm", "rewrite")
push = subprocess.Popen(["git", "push", "-q", "-f", "origin", "main"], cwd=repo, env=ENV,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
wait_pending()
check("force push is flagged risky", any(p["risky"] for p in status()["pending"]), str(status()["pending"]))
r = press(2, "tap")
check("a tap allows the force push", r == "allow" and push.wait(15) == 0, r)

# ---------------------------------------------------------------- chat bridge (MCP)
async def mcp_test():
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    params = StdioServerParameters(command=PY, args=["-m", "nod.cli", "mcp"],
                                   env=dict(ENV, NOD_MCP_WAIT="1.5", NOD_SOURCE="chat"))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = sorted(t.name for t in (await s.list_tools()).tools)
            check("MCP server lists its tools", tools == ["check_approval", "notify_done", "request_approval"], str(tools))
            res = await s.call_tool("request_approval", {"action": "Send email", "target": "to: booking@venue.com"})
            txt = res.content[0].text
            check("long wait returns PENDING with a ticket", txt.startswith("PENDING"), txt)
            ticket = txt.split("ticket=")[1].rstrip(".")
            await asyncio.to_thread(press, 0)
            txt = (await s.call_tool("check_approval", {"ticket": ticket})).content[0].text
            check("check_approval gets APPROVED after the press", txt.startswith("APPROVED"), txt)
            task = asyncio.create_task(s.call_tool("request_approval", {"action": "Delete folder", "target": "~/Photos/2024"}))
            await asyncio.sleep(0.6)
            pend = await asyncio.to_thread(status)
            check("chat delete is flagged risky by the action text", bool(pend["pending"]) and pend["pending"][0]["risky"], str(pend["pending"]))
            await asyncio.to_thread(press, 0, "double")
            txt = (await task).content[0].text
            check("double-tap returns DENIED to the chat", txt.startswith("DENIED"), txt)
            txt = (await s.call_tool("notify_done", {"message": "Drafted 12 venue emails"})).content[0].text
            check("notify_done shows on the key", txt == "Shown on the key.", txt)

asyncio.run(mcp_test())

daemon.terminate()
print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
