"""Tiny stdlib-only client for the daemon, so hooks start fast and need no extra installs."""
import json
import urllib.error
import urllib.request

from . import config


def _call(method, path, body=None, timeout=10):
    cfg = config.load()
    url = f"http://127.0.0.1:{cfg['port']}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Nod-Token": config.token()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ask(source, l1, l2="", l3="", risky=False, wait=None, ttl=None):
    """Blocks until the key answers. Returns allow | deny | timeout | unavailable | pending."""
    body = {"source": source, "l1": l1, "l2": l2, "l3": l3, "risky": risky}
    if ttl:
        body["ttl"] = ttl
    if wait is not None:
        body["wait"] = wait
    try:
        return _call("POST", "/v1/ask", body, timeout=(wait or 600) + 15)
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return {"decision": "unavailable"}


def poll(rid, wait=45):
    try:
        return _call("GET", f"/v1/ask/{rid}?wait={wait}", timeout=wait + 15)
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return {"decision": "unavailable"}


def notify(source, l1, l2=""):
    try:
        return _call("POST", "/v1/notify", {"source": source, "l1": l1, "l2": l2})
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return {"queued": False}


def status():
    return _call("GET", "/v1/status")


def sim_press(lane, kind="tap"):
    return _call("POST", "/v1/sim/press", {"lane": lane, "kind": kind})
