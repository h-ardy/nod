"""Paths, defaults and the shared secret for the local Nod daemon."""
import json
import os
import secrets
from pathlib import Path

HOME = Path(os.environ.get("NOD_HOME", Path.home() / ".nod"))
CONFIG_PATH = HOME / "config.json"
TOKEN_PATH = HOME / "token"

DEFAULTS = {
    "port": 47823,
    # BLE addresses in lane order (left to right). `nod pair` fills this in.
    "lanes": [],
    # which lane each source prefers; a missing or offline lane falls back to the least busy one
    "routes": {"claude-code": 0, "gemini": 1, "git": 2, "codex": 3, "chat": 0},
    "colors": {
        "claude-code": "D97757", "chat": "D97757", "codex": "E8E6E1",
        "gemini": "5B8DEF", "git": "3FB950", "*": "E5B53A",
    },
    "labels": {
        "claude-code": "CLAUDE CODE", "chat": "CLAUDE CHAT", "codex": "CODEX",
        "gemini": "GEMINI CLI", "git": "GIT PUSH",
    },
    # seconds a request may sit on a key before it is withdrawn
    "ask_ttl": 540,
}


def load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_PATH.exists():
        user = json.loads(CONFIG_PATH.read_text())
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def save(cfg: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def token() -> str:
    """Random token that every local caller must send, so a web page cannot POST approvals to localhost."""
    HOME.mkdir(parents=True, exist_ok=True)
    if not TOKEN_PATH.exists():
        TOKEN_PATH.write_text(secrets.token_urlsafe(24))
        os.chmod(TOKEN_PATH, 0o600)
    return TOKEN_PATH.read_text().strip()
