"""Turn a raw request into the three short lines a tile shows, and flag risky ones.

The text always comes from the real command, path or URL, never from the model's
own description of what it is about to do.
"""
import json
import os
import re

RISKY = [
    (r"\brm\s+-[a-zA-Z]*[rf]", "rm -r/-f"),
    (r"\bsudo\b", "sudo"),
    (r"\bgit\s+push\b.*(--force\b|--force-with-lease|\s-f\b|\s\+\S)", "force push"),
    (r"\bgit\s+reset\s+--hard", "reset --hard"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean -f"),
    (r"\bgit\s+branch\s+-D\b", "branch -D"),
    (r"(curl|wget)\b[^|;]*\|\s*(sudo\s+)?(ba|z|da)?sh\b", "pipe to shell"),
    (r"\bchmod\s+(-R\s+)?0?777\b", "chmod 777"),
    (r"\bmkfs(\.\w+)?\b", "mkfs"),
    (r"\bdd\s+[^|]*\bof=", "dd"),
    (r">\s*/dev/(sd|disk|nvme)", "raw disk write"),
    (r"\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b", "publish"),
    (r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b|\bTRUNCATE\s+TABLE\b", "drop table"),
    (r"\bkubectl\s+delete\b|\bterraform\s+(destroy|apply)\b", "infra change"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
]
# extra words that make a chat action risky (chat requests are prose, not shell commands)
CHAT_RISKY = re.compile(r"\b(delete|remove|erase|wipe|purchase|buy|order|pay|payment|transfer|wire|"
                        r"unsubscribe|cancel|publish|post publicly|send money)\b", re.IGNORECASE)
SENSITIVE_PATH = re.compile(r"(^|/)(\.env[^/]*|\.ssh/|\.aws/|\.gnupg/|id_rsa|id_ed25519|.*\.pem$|\.git/)")


def risk_of(text: str):
    for pat, label in RISKY:
        if re.search(pat, text, re.IGNORECASE):
            return label
    return None


def clip(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _rel(path: str, cwd: str) -> str:
    try:
        r = os.path.relpath(path, cwd)
        return path if r.startswith("..") else r
    except ValueError:
        return path


def claude_permission(evt: dict) -> dict:
    """Summary for a Claude Code PermissionRequest hook event."""
    tool = evt.get("tool_name", "?")
    ti = evt.get("tool_input") or {}
    cwd = evt.get("cwd") or os.getcwd()
    where = os.path.basename(cwd.rstrip("/")) or cwd
    risky = None
    if tool == "Bash":
        cmd = ti.get("command", "")
        l1, l2 = "Bash", clip(cmd.splitlines()[0] if cmd else "", 60)
        risky = risk_of(cmd)
    elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read"):
        p = ti.get("file_path") or ti.get("notebook_path") or ""
        l1, l2 = tool, clip(_rel(p, cwd), 60)
        if SENSITIVE_PATH.search(p) and tool != "Read":
            risky = "sensitive file"
        elif not os.path.abspath(p).startswith(os.path.abspath(cwd)) and tool != "Read":
            risky = "outside project"
    elif tool == "WebFetch":
        l1, l2 = "WebFetch", clip(re.sub(r"^https?://", "", ti.get("url", "")), 60)
    elif tool == "WebSearch":
        l1, l2 = "WebSearch", clip(ti.get("query", ""), 60)
    elif tool.startswith("mcp__"):
        parts = tool.split("__")
        l1 = clip(parts[1] if len(parts) > 1 else tool, 20)
        l2 = clip((parts[2] if len(parts) > 2 else "") + " " + json.dumps(ti)[:80], 60)
    else:
        l1, l2 = clip(tool, 20), clip(json.dumps(ti), 60)
    l3 = where if not risky else f"{where}  RISK: {risky}"
    return {"l1": l1, "l2": l2, "l3": clip(l3, 40), "risky": bool(risky)}
