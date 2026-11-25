"""The Nod daemon: one local process that owns the Bluetooth links to the keys.

Hooks, git and the chat bridge talk to it over HTTP on 127.0.0.1 (token required).
It queues requests, puts each one on a lane, and resolves it when that key answers.
The Nod Dot app listens on /v1/events (WebSocket) and shows a request in full when the key is held.
It can open and close its panel, but it can never answer a request: only a key press does that.

Wire protocol to a key: newline-delimited JSON over the Nordic UART Service.
  host -> key  {"t":"add","id","src","c","l1","l2","l3","risk"}   new approval tile
               {"t":"note","id","src","c","l1","l2"}                info tile, tap to clear
               {"t":"del","id"}                                     withdraw a tile
               {"t":"lane","n"}                                     lane number to show
               {"t":"pair"}                                         show "PRESS ME"
               {"t":"more","n"}                                     how many more are parked here
               {"t":"open","id","code"}                             the Nod Dot panel is showing this request
               {"t":"shut","id"}                                    the panel closed without an answer
               {"t":"nolook","id"}                                  no Nod Dot app is running to show it
  key -> host  {"t":"ans","id","d":"allow"|"deny"}                  decision
               {"t":"ack","id"}                                     note cleared
               {"t":"btn"}                                          press with nothing showing
               {"t":"look","id"}                                    held: show me this request in full
               {"t":"hello","fw","bat"}                             on connect
"""
import asyncio
import json
import secrets
import time
from aiohttp import web

from . import config

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"   # host writes here
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   # key notifies here
CHUNK = 20                                        # safe for the default 23-byte ATT MTU
CODE_ALPHABET = "ACDEFHJKMNPRTVWXY347"           # no 0/O, 1/I/L, 2/Z, 5/S, 8/B: easy to compare at a glance


class Request:
    def __init__(self, kind, source, l1, l2="", l3="", risky=False, ttl=540, detail="", why=""):
        self.id = secrets.token_hex(4)
        self.code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(3))   # same code on key and panel
        self.detail, self.why = detail, why
        self.opened = False         # the Nod Dot panel is showing it right now
        self.kind, self.source = kind, source
        self.l1, self.l2, self.l3, self.risky = l1, l2, l3, risky
        self.ttl = ttl
        self.created = time.time()
        self.lane = None
        self.shown = False          # on the key's screen, or still parked in the daemon's queue
        self.decision = None
        self.done = asyncio.Event()


# ------------------------------------------------------------------ links
class Link:
    """One physical (or simulated) key."""
    lane: int
    connected = False

    async def send(self, obj):
        raise NotImplementedError


class BleLink(Link):
    def __init__(self, broker, lane, address):
        self.broker, self.lane, self.address = broker, lane, address
        self.client, self.buf = None, b""

    async def run(self):
        from bleak import BleakClient
        while True:
            try:
                async with BleakClient(self.address) as c:
                    self.client = c
                    await c.start_notify(NUS_TX, self._on_notify)
                    self.connected = True
                    print(f"[ble] lane {self.lane} connected {self.address}")
                    await self.send({"t": "lane", "n": self.lane + 1})
                    await self.broker.resend_lane(self.lane)
                    while c.is_connected:
                        await asyncio.sleep(1)
            except Exception as e:  # noqa: BLE001  keep retrying whatever the radio stack throws
                print(f"[ble] lane {self.lane} {self.address}: {e}")
            self.connected = False
            await asyncio.sleep(3)

    def _on_notify(self, _char, data: bytearray):
        self.buf += bytes(data)
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            try:
                self.broker.on_key(self.lane, json.loads(line))
            except json.JSONDecodeError:
                pass

    async def send(self, obj):
        if not (self.client and self.connected):
            return
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
        for i in range(0, len(data), CHUNK):
            await self.client.write_gatt_char(NUS_RX, data[i:i + CHUNK], response=True)


class SimLink(Link):
    """A key that lives in the terminal. Press it with POST /v1/sim/press."""

    def __init__(self, broker, lane):
        self.broker, self.lane, self.connected = broker, lane, True
        self.tiles = []        # mirrors what the real firmware keeps
        self.more = 0          # requests parked on the laptop behind this key

    def state(self, msg=""):
        """What this key's screen would show, for the practice key window in Nod Dot."""
        return {"ev": "sim", "lane": self.lane, "more": self.more, "msg": msg,
                "tiles": [{k: t.get(k) for k in ("id", "t", "src", "c", "l1", "l2", "l3", "risk", "code", "opened", "nolook")}
                          for t in self.tiles]}

    async def send(self, obj):
        t = obj.get("t")
        if t in ("add", "note"):
            self.tiles.append(dict(obj, opened=False))
            tag = "RISKY " if obj.get("risk") else ""
            print(f"[sim lane {self.lane + 1}] {tag}{obj['src']}: {obj['l1']} | {obj.get('l2', '')}  code {obj.get('code', '')}")
        elif t == "del":
            self.tiles = [x for x in self.tiles if x["id"] != obj["id"]]
        elif t in ("open", "shut"):
            for x in self.tiles:
                if x["id"] == obj["id"]:
                    x["opened"] = t == "open"
        elif t == "nolook":
            for x in self.tiles:
                if x["id"] == obj["id"]:
                    x["nolook"] = True
            print(f"[sim lane {self.lane + 1}] no Nod Dot app is running: hold again to run")
        elif t == "more":
            self.more = int(obj.get("n", 0))
        self.broker.emit_key(self.state())

    def press(self, kind):
        res = self._press(kind)
        self.broker.emit_key(self.state(res))
        return res

    def _press(self, kind):
        """Same rules as the firmware: tap approves, double-tap denies, hold opens the request on screen.
        Risky requests take the same controls; they only look different (red). With no Nod Dot app
        running, the key says so and a second hold runs it."""
        if not self.tiles:
            self.broker.on_key(self.lane, {"t": "btn"})
            return "nothing on this lane"
        tile = self.tiles[0]
        if tile["t"] == "note":
            self.tiles.pop(0)
            self.broker.on_key(self.lane, {"t": "ack", "id": tile["id"]})
            return "note cleared"
        if kind == "hold" and tile.get("nolook"):
            d = "allow"                           # no screen to show it on: a second hold runs it
        elif kind == "hold":
            self.broker.on_key(self.lane, {"t": "look", "id": tile["id"]})
            return "look"
        elif kind == "double":
            d = "deny"
        else:
            d = "allow"
        self.tiles.pop(0)
        self.broker.on_key(self.lane, {"t": "ans", "id": tile["id"], "d": d})
        return d


# ------------------------------------------------------------------ broker
class Broker:
    def __init__(self, cfg, sim=0):
        self.cfg = cfg
        self.links: dict[int, Link] = {}
        self.requests: dict[str, Request] = {}   # still on a key
        self.all: dict[str, Request] = {}        # every request, so a late poll still gets its answer
        self.pair_order = None
        self.watchers: set = set()               # Nod Dot apps listening on /v1/events
        self.key_watchers: set = set()           # practice key windows: they see simulated screens only
        self._locks: dict[int, asyncio.Lock] = {}
        if sim:
            for i in range(sim):
                self.links[i] = SimLink(self, i)
        else:
            for i, addr in enumerate(cfg.get("lanes", [])):
                self.links[i] = BleLink(self, i, addr)

    def live_links(self):
        return {i: l for i, l in self.links.items() if l.connected}

    def pick_lane(self, source):
        live = self.live_links()
        if not live:
            return None
        want = self.cfg["routes"].get(source)
        if want in live:
            return want
        load = {i: sum(1 for r in self.requests.values() if r.lane == i) for i in live}
        return min(load, key=load.get)

    def _payload(self, r: Request):
        colors, labels = self.cfg["colors"], self.cfg["labels"]
        return {
            "t": "add" if r.kind == "ask" else "note", "id": r.id,
            "src": labels.get(r.source, r.source.upper())[:16],
            "c": colors.get(r.source, colors["*"]),
            "l1": r.l1[:24], "l2": r.l2[:60], "l3": r.l3[:40], "risk": 1 if r.risky else 0,
            "code": r.code,
        }

    # ---- Nod Dot: live events for the on-screen panel
    def public(self, r: Request):
        labels, colors = self.cfg["labels"], self.cfg["colors"]
        return {"id": r.id, "kind": r.kind, "source": r.source, "label": labels.get(r.source, r.source.upper()),
                "color": "#" + colors.get(r.source, colors["*"]), "l1": r.l1, "l2": r.l2, "l3": r.l3,
                "risky": r.risky, "code": r.code, "detail": r.detail, "why": r.why, "lane": r.lane,
                "created": r.created, "opened": r.opened}

    def emit_key(self, ev: dict):
        for ws in list(self.key_watchers):
            try:
                asyncio.ensure_future(ws.send_json(ev))
            except Exception:  # noqa: BLE001
                self.key_watchers.discard(ws)

    def emit(self, ev: dict):
        dead = []
        for ws in list(self.watchers):
            try:
                asyncio.ensure_future(ws.send_json(ev))
            except Exception:  # noqa: BLE001  a closed socket: drop it
                dead.append(ws)
        for ws in dead:
            self.watchers.discard(ws)

    async def look(self, lane, rid):
        """The key was held on a request: open it on screen, or tell the key nobody is watching."""
        r = self.requests.get(rid)
        if not r:
            return
        if not self.watchers:
            await self.links[lane].send({"t": "nolook", "id": rid})
            return
        self.emit({"ev": "look", "req": self.public(r)})

    async def panel(self, rid, is_open: bool):
        """The Nod Dot app opened or closed its panel. Tell the key, so it can take a plain tap."""
        r = self.requests.get(rid)
        if not r or r.lane not in self.links:
            return
        r.opened = is_open
        await self.links[r.lane].send({"t": "open", "id": rid, "code": r.code} if is_open else {"t": "shut", "id": rid})

    # The screen fits 3 tiles above the line. The daemon puts at most MAX_ON_KEY on a key at once and
    # parks the rest, showing the next one as soon as a slot frees up. The key shows "+N MORE".
    MAX_ON_KEY = 3

    def _on_lane(self, lane, shown):
        return [r for r in sorted(self.requests.values(), key=lambda x: x.created)
                if r.lane == lane and r.shown == shown and not r.done.is_set()]

    async def _show(self, r: Request):
        r.shown = True
        await self.links[r.lane].send(self._payload(r))

    async def refill(self, lane):
        """Move parked requests onto the key while it has room, then update its +N counter."""
        if lane not in self.links:
            return
        lock = self._locks.setdefault(lane, asyncio.Lock())   # many requests can arrive at once
        async with lock:
            parked = self._on_lane(lane, shown=False)
            room = self.MAX_ON_KEY - len(self._on_lane(lane, shown=True))
            for r in parked[:max(room, 0)]:
                await self._show(r)
            await self.links[lane].send({"t": "more", "n": len(self._on_lane(lane, shown=False))})

    async def submit(self, r: Request):
        r.lane = self.pick_lane(r.source)
        if r.lane is None:
            r.decision = "unavailable"
            r.done.set()
            return r
        self.requests[r.id] = r
        self.all[r.id] = r
        self.emit({"ev": "add", "req": self.public(r)})
        await self.refill(r.lane)
        asyncio.get_running_loop().call_later(r.ttl, lambda: asyncio.ensure_future(self.expire(r)))
        return r

    async def _retire(self, r: Request, decision: str):
        """Resolve a request that the key did not answer: take its tile off (if shown) and refill."""
        if not r.done.is_set():
            r.decision = decision
            r.done.set()
        if self.requests.pop(r.id, None):
            self.emit({"ev": "done", "id": r.id, "decision": decision})
        if r.lane in self.links:
            if r.shown:
                await self.links[r.lane].send({"t": "del", "id": r.id})
            await self.refill(r.lane)

    async def expire(self, r: Request):
        if not r.done.is_set():
            await self._retire(r, "timeout")

    async def withdraw(self, r: Request):
        """Caller gave up (hook killed, terminal answered first): take the tile off the key."""
        await self._retire(r, "withdrawn")

    async def resend_lane(self, lane):
        for r in self._on_lane(lane, shown=True):
            await self.links[lane].send(self._payload(r))
        await self.refill(lane)

    def on_key(self, lane, msg):
        t = msg.get("t")
        if t in ("ans", "ack"):
            r = self.requests.pop(msg.get("id"), None)
            if r and not r.done.is_set():
                r.decision = ("allow" if msg.get("d") == "allow" else "deny") if t == "ans" else "seen"
                r.done.set()
            if r:
                self.emit({"ev": "done", "id": r.id, "decision": r.decision})
            asyncio.ensure_future(self.refill(lane))       # a slot just opened on this key
        elif t == "btn" and self.pair_order is not None and lane not in self.pair_order:
            self.pair_order.append(lane)
        elif t == "look":
            asyncio.ensure_future(self.look(lane, msg.get("id")))
        elif t == "hello":
            print(f"[key {lane + 1}] firmware {msg.get('fw')} battery {msg.get('bat')}%")


# ------------------------------------------------------------------ http api
def make_app(broker: Broker, tok: str):
    routes = web.RouteTableDef()

    @web.middleware
    async def auth(request, handler):
        given = request.headers.get("X-Nod-Token") or (request.query.get("token") if request.path == "/v1/events" else None)
        if given != tok:
            return web.json_response({"error": "bad token"}, status=401)
        return await handler(request)

    async def wait_for(r: Request, wait: float):
        try:
            await asyncio.wait_for(r.done.wait(), timeout=wait)
        except asyncio.TimeoutError:
            return {"decision": "pending", "id": r.id, "lane": r.lane}
        return {"decision": r.decision, "id": r.id, "lane": r.lane}

    @routes.post("/v1/ask")
    async def ask(request):
        b = await request.json()
        r = Request("ask", b.get("source", "*"), b.get("l1", "?"), b.get("l2", ""), b.get("l3", ""),
                    bool(b.get("risky")), int(b.get("ttl", broker.cfg["ask_ttl"])),
                    detail=str(b.get("detail", ""))[:20000], why=str(b.get("why", ""))[:600])
        await broker.submit(r)
        wait = float(b.get("wait", r.ttl))
        try:
            return web.json_response(await wait_for(r, wait))
        except asyncio.CancelledError:          # caller hung up while waiting
            await broker.withdraw(r)
            raise

    @routes.get("/v1/ask/{rid}")
    async def poll(request):
        r = broker.all.get(request.match_info["rid"])
        if r is None:
            return web.json_response({"decision": "unknown"})
        return web.json_response(await wait_for(r, float(request.query.get("wait", 45))))

    @routes.delete("/v1/ask/{rid}")
    async def cancel(request):
        r = broker.requests.get(request.match_info["rid"])
        if r:
            await broker.withdraw(r)
        return web.json_response({"ok": True})

    @routes.post("/v1/notify")
    async def notify(request):
        b = await request.json()
        r = Request("note", b.get("source", "*"), b.get("l1", ""), b.get("l2", ""), ttl=3600)
        await broker.submit(r)
        return web.json_response({"queued": r.decision != "unavailable", "id": r.id})

    @routes.get("/v1/status")
    async def status(request):
        return web.json_response({
            "lanes": {i: {"connected": l.connected} for i, l in broker.links.items()},
            "pending": [{"id": r.id, "source": r.source, "l1": r.l1, "lane": r.lane, "risky": r.risky,
                         "shown": r.shown}
                        for r in broker.requests.values()],
        })

    @routes.post("/v1/pair")
    async def pair(request):
        broker.pair_order = []
        for l in broker.live_links().values():
            await l.send({"t": "pair"})
        n = len(broker.live_links())
        for _ in range(120):
            if len(broker.pair_order) >= n:
                break
            await asyncio.sleep(0.5)
        order, broker.pair_order = broker.pair_order, None
        return web.json_response({"order": order})

    @routes.get("/v1/events")
    async def events(request):
        """Nod Dot app: a snapshot, then live events. It may only open and close its panel."""
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        if request.query.get("role") == "key":
            # A practice key window. It only watches simulated screens; it does not count as a
            # Nod Dot app, and it cannot open, close or answer anything over this socket.
            broker.key_watchers.add(ws)
            try:
                sims = [l for l in broker.links.values() if isinstance(l, SimLink)]
                await ws.send_json({"ev": "keyhello", "sim": bool(sims)})
                for l in sims:
                    await ws.send_json(l.state())
                async for _ in ws:
                    pass
            finally:
                broker.key_watchers.discard(ws)
            return ws
        broker.watchers.add(ws)
        await ws.send_json({"ev": "hello", "pending": [broker.public(r) for r in broker.requests.values()
                                                       if r.kind == "ask"]})
        try:
            async for m in ws:
                if m.type != web.WSMsgType.TEXT:
                    continue
                try:
                    cmd = json.loads(m.data)
                except json.JSONDecodeError:
                    continue
                if cmd.get("cmd") in ("opened", "closed"):
                    await broker.panel(str(cmd.get("id")), cmd["cmd"] == "opened")
        finally:
            broker.watchers.discard(ws)
            for r in broker.requests.values():          # the panel is gone with the app
                if r.opened:
                    await broker.panel(r.id, False)
        return ws

    @routes.post("/v1/sim/press")
    async def sim_press(request):
        b = await request.json()
        link = broker.links.get(int(b["lane"]))
        if not isinstance(link, SimLink):
            return web.json_response({"error": "not a simulated lane"}, status=400)
        return web.json_response({"result": link.press(b.get("kind", "tap"))})

    app = web.Application(middlewares=[auth])
    app.add_routes(routes)
    return app


async def main(sim=0):
    cfg = config.load()
    broker = Broker(cfg, sim=sim)
    for l in broker.links.values():
        if isinstance(l, BleLink):
            asyncio.ensure_future(l.run())
    # handler_cancellation: if a hook process dies mid-wait, its tile is withdrawn from the key
    runner = web.AppRunner(make_app(broker, config.token()), handler_cancellation=True)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", cfg["port"]).start()
    mode = f"simulating {sim} keys" if sim else f"{len(broker.links)} keys configured"
    print(f"nod daemon on 127.0.0.1:{cfg['port']} ({mode})", flush=True)
    await asyncio.Event().wait()
