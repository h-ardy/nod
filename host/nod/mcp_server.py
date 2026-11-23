"""Chat bridge: an MCP server that chat apps (Claude Desktop and other MCP clients) launch over stdio.

The model calls `request_approval` before anything with side effects and only goes ahead on
APPROVED. Unlike the Claude Code hook, this is cooperative: it works because the model is told
to use it, not because the app forces it. Keep the app's own confirmations on for anything that
matters, and set this server's tools to "always allow" so the key is where you answer.

Chat apps time out long tool calls, so a call waits at most WAIT seconds and then returns
PENDING with a ticket; the model calls `check_approval(ticket)` to keep waiting.
"""
import asyncio
import os

from . import client, summarize

try:                                   # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                    # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

SOURCE = os.environ.get("NOD_SOURCE", "chat")
WAIT = float(os.environ.get("NOD_MCP_WAIT", "45"))

INSTRUCTIONS = (
    "The user approves actions on a physical key. Before any action with side effects "
    "(sending or posting anything, deleting, purchasing, writing or moving files, running code, "
    "changing settings), call request_approval with a short action and the exact target. "
    "Proceed only if the result starts with APPROVED. If it starts with PENDING, call "
    "check_approval with the ticket until you get an answer. If DENIED, do not do it and say so. "
    "When a long task finishes, call notify_done with one short line."
)

server = _Server(name="nod", instructions=INSTRUCTIONS)


def _word(res):
    d = res.get("decision")
    if d == "allow":
        return "APPROVED. Go ahead with exactly this action."
    if d == "deny":
        return "DENIED by the user on the key. Do not perform this action."
    if d == "pending":
        return f"PENDING. Still on the key. Call check_approval with ticket={res['id']}."
    return f"UNAVAILABLE ({d}). Ask the user in the chat instead."


@server.tool()
async def request_approval(action: str, target: str = "", risky: bool = False) -> str:
    """Ask the user to approve one action on their Nod key. action: a few words, e.g. 'Send email'.
    target: the exact thing affected, e.g. the recipient, file path, URL or command."""
    text = f"{action} {target}"
    flag = risky or bool(summarize.risk_of(text)) or bool(summarize.CHAT_RISKY.search(action))
    res = await asyncio.to_thread(client.ask, SOURCE, summarize.clip(action, 24),
                                  summarize.clip(target, 60), "", flag, WAIT,
                                  detail=f"Action: {action}\nTarget: {target}")
    return _word(res)


@server.tool()
async def check_approval(ticket: str) -> str:
    """Keep waiting on a PENDING approval."""
    return _word(await asyncio.to_thread(client.poll, ticket, WAIT))


@server.tool()
async def notify_done(message: str) -> str:
    """Put a 'done' note on the user's key so they know to come back."""
    res = await asyncio.to_thread(client.notify, SOURCE, "Done", summarize.clip(message, 60))
    return "Shown on the key." if res.get("queued") else "Key not available."


def run():
    server.run()
