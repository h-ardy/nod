"""nod: command line entry point.

  nod daemon [--sim N]          run the daemon (or N fake keys in the terminal)
  nod pair                      find keys and set lane order by pressing them left to right
  nod hook claude               Claude Code hook handler (PermissionRequest, Stop, Notification)
  nod git-pre-push REMOTE URL   git pre-push hook body
  nod install-git [REPO]        install the pre-push hook into a repo
  nod claude-settings           print the hooks block for ~/.claude/settings.json
  nod mcp                       chat bridge (MCP server over stdio) for Claude Desktop and other MCP chat apps
  nod ask / notify / status / press   manual and test helpers
"""
import argparse
import asyncio
import json
import os
import stat
import subprocess
import sys

from . import client, config, summarize

ZERO = "0" * 40


# ------------------------------------------------------------------ Claude Code
def hook_claude():
    evt = json.load(sys.stdin)
    name = evt.get("hook_event_name")
    if name == "PermissionRequest":
        s = summarize.claude_permission(evt)
        res = client.ask("claude-code", s["l1"], s["l2"], s["l3"], s["risky"], detail=s["detail"], why=s["why"])
        d = res.get("decision")
        if d == "allow":
            out = {"behavior": "allow"}
        elif d == "deny":
            out = {"behavior": "deny", "message": "The user denied this on their Nod key."}
        else:
            # key offline, timed out or withdrawn: print nothing, so Claude Code shows its normal dialog
            return 0
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": out}}))
        return 0
    if name == "Stop":
        msg = (evt.get("last_assistant_message") or "").strip().splitlines()
        where = os.path.basename((evt.get("cwd") or "").rstrip("/"))
        client.notify("claude-code", "Done", summarize.clip((msg[0] if msg else where), 60))
        return 0
    if name == "Notification" and evt.get("notification_type") in ("idle_prompt", "agent_needs_input"):
        client.notify("claude-code", "Waiting for you", summarize.clip(evt.get("message", ""), 60))
        return 0
    return 0


CLAUDE_SETTINGS = {
    "hooks": {
        "PermissionRequest": [{"hooks": [{"type": "command", "command": "nod hook claude", "timeout": 600}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "nod hook claude", "timeout": 10}]}],
        "Notification": [{"matcher": "idle_prompt",
                          "hooks": [{"type": "command", "command": "nod hook claude", "timeout": 10}]}],
    }
}


# ------------------------------------------------------------------ git
def _git(*args, cwd=None):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd).stdout.strip()


def git_pre_push(remote, url):
    """git passes '<local ref> <local sha> <remote ref> <remote sha>' lines on stdin."""
    strict = os.environ.get("NOD_GIT_STRICT") == "1"
    repo = os.path.basename(_git("rev-parse", "--show-toplevel"))
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        lref, lsha, rref, rsha = parts
        branch = rref.replace("refs/heads/", "")
        risky = False
        if lsha == ZERO:
            l2, risky = f"DELETE {branch}", True
        else:
            if rsha == ZERO:
                n = _git("rev-list", "--count", lsha, "--not", "--remotes=" + remote) or "?"
                base = None
            else:
                n = _git("rev-list", "--count", f"{rsha}..{lsha}") or "?"
                base = rsha
                if subprocess.run(["git", "merge-base", "--is-ancestor", rsha, lsha]).returncode != 0:
                    risky = True
            stat_line = _git("diff", "--shortstat", f"{base}..{lsha}") if base else ""
            plus = minus = 0
            for tok in stat_line.split(","):
                tok = tok.strip()
                if "insertion" in tok:
                    plus = int(tok.split()[0])
                if "deletion" in tok:
                    minus = int(tok.split()[0])
            l2 = f"{n} commit{'s' if n != '1' else ''} +{plus} -{minus}"
            if risky:
                l2 = "FORCE  " + l2
        if lsha == ZERO:
            detail = f"Deletes the branch {branch} on {remote} ({url})."
        else:
            rng = [lsha, "--not", "--remotes=" + remote] if rsha == ZERO else [f"{rsha}..{lsha}"]
            commits = _git("log", "--oneline", "--no-decorate", "-n", "50", *rng)
            files = _git("diff", "--stat", f"{rsha}..{lsha}") if rsha != ZERO else ""
            detail = (f"Push {branch} to {remote} ({url})\n"
                      + ("This rewrites history on the remote (force push).\n" if risky else "")
                      + "\nCommits:\n" + (commits or "(none found)") + ("\n\nFiles:\n" + files if files else ""))
        res = client.ask("git", f"{branch} to {remote}", l2, repo, risky, detail=detail)
        d = res.get("decision")
        if d == "deny":
            print(f"nod: push of {branch} denied on the key", file=sys.stderr)
            return 1
        if d != "allow":
            if strict:
                print(f"nod: key unavailable ({d}); NOD_GIT_STRICT=1 so not pushing", file=sys.stderr)
                return 1
            print(f"nod: key unavailable ({d}); pushing without it", file=sys.stderr)
    return 0


def install_git(repo):
    hooks = os.path.join(_git("rev-parse", "--git-common-dir", cwd=repo) or ".git", "hooks")
    if not os.path.isabs(hooks):
        hooks = os.path.join(repo, hooks)
    path = os.path.join(hooks, "pre-push")
    with open(path, "w") as f:
        f.write(f'#!/bin/sh\nexec "{sys.executable}" -m nod.cli git-pre-push "$@"\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print("installed", path)


# ------------------------------------------------------------------ pairing
def is_nod_name(name):
    """Keys advertise as Nod-XXXX, or Claude-Nod-XXXX in desktop-app mode."""
    name = name or ""
    return name.startswith("Nod-") or name.startswith("Claude-Nod-")


async def pair():
    from bleak import BleakScanner, BleakClient
    from .daemon import NUS_TX, NUS_RX
    print("Scanning 6 s for Nod keys ...")
    found = [d for d in await BleakScanner.discover(timeout=6) if is_nod_name(d.name)]
    if not found:
        print("No keys found. Is the daemon running? Stop it first; a key only talks to one host.")
        return 1
    print(f"Found {len(found)}. Every key now says PRESS. Press them from LEFT to RIGHT.")
    order, clients = [], []
    for d in found:
        c = BleakClient(d)
        await c.connect()
        clients.append(c)

        def cb(_ch, data, addr=d.address):
            if b'"btn"' in bytes(data) and addr not in order:
                order.append(addr)
                print(f"  lane {len(order)}: {addr}")
        await c.start_notify(NUS_TX, cb)
        await c.write_gatt_char(NUS_RX, b'{"t":"pair"}\n', response=True)
    for _ in range(240):
        if len(order) == len(found):
            break
        await asyncio.sleep(0.25)
    for c in clients:
        await c.disconnect()
    cfg = config.load()
    cfg["lanes"] = order
    config.save(cfg)
    print("Saved lane order to", config.CONFIG_PATH)
    return 0


# ------------------------------------------------------------------ main
def main(argv=None):
    p = argparse.ArgumentParser(prog="nod")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daemon"); d.add_argument("--sim", type=int, default=0)
    sub.add_parser("pair")
    h = sub.add_parser("hook"); h.add_argument("agent", choices=["claude"])
    g = sub.add_parser("git-pre-push"); g.add_argument("remote"); g.add_argument("url")
    ig = sub.add_parser("install-git"); ig.add_argument("repo", nargs="?", default=".")
    sub.add_parser("claude-settings")
    sub.add_parser("mcp")
    a = sub.add_parser("ask")
    a.add_argument("--source", default="*"); a.add_argument("--l1", required=True)
    a.add_argument("--l2", default=""); a.add_argument("--l3", default="")
    a.add_argument("--risky", action="store_true"); a.add_argument("--wait", type=float)
    a.add_argument("--detail", default="", help="full text for the Nod Dot panel"); a.add_argument("--why", default="")
    n = sub.add_parser("notify"); n.add_argument("--source", default="*"); n.add_argument("--l1", required=True); n.add_argument("--l2", default="")
    sub.add_parser("status")
    pr = sub.add_parser("press"); pr.add_argument("lane", type=int); pr.add_argument("kind", nargs="?", default="tap")
    args = p.parse_args(argv)

    if args.cmd == "daemon":
        from . import daemon
        asyncio.run(daemon.main(sim=args.sim))
    elif args.cmd == "pair":
        return asyncio.run(pair())
    elif args.cmd == "hook":
        return hook_claude()
    elif args.cmd == "git-pre-push":
        return git_pre_push(args.remote, args.url)
    elif args.cmd == "install-git":
        install_git(args.repo)
    elif args.cmd == "claude-settings":
        print(json.dumps(CLAUDE_SETTINGS, indent=2))
    elif args.cmd == "mcp":
        from . import mcp_server
        mcp_server.run()
    elif args.cmd == "ask":
        res = client.ask(args.source, args.l1, args.l2, args.l3, args.risky, wait=args.wait,
                         detail=args.detail, why=args.why)
        print(res.get("decision"))
        return {"allow": 0, "deny": 1}.get(res.get("decision"), 2)
    elif args.cmd == "notify":
        print(client.notify(args.source, args.l1, args.l2))
    elif args.cmd == "status":
        print(json.dumps(client.status(), indent=2))
    elif args.cmd == "press":
        print(client.sim_press(args.lane, args.kind))
    return 0


if __name__ == "__main__":
    sys.exit(main())
