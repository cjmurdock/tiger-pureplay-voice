"""Pureplay Accessory API client (WebSocket, protocol version 1).

See https://github.com/PureplayGolf/Pureplay-Accessory/blob/main/docs/protocol.md
"""
import asyncio
import itertools
import json
import logging
import os

import websockets

log = logging.getLogger("tiger.api")


class ApiError(Exception):
    def __init__(self, code, message="", blockers=None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.blockers = blockers or []


class PurePlayClient:
    SUBSCRIBE_EVENTS = ["shot.*", "turn.changed", "hole.started", "match.*",
                        "context.invalidated", "player.bag_changed"]

    def __init__(self, host, port, client_name, token_path, on_event=None, on_status=None):
        self.uri = f"ws://{host}:{port}/"
        self.client_name = client_name[:64]
        self.token_path = token_path
        self.on_event = on_event          # async fn(event_name, data)
        self.on_status = on_status        # fn(text) for user-facing status messages
        self.ws = None
        self.connected = asyncio.Event()
        self.scopes = []
        self._ids = itertools.count(1)
        self._pending = {}                # id -> Future (responses and requested snapshots)
        self._server_instance = None
        self._tasks = set()

    # ---------- token ----------
    def _load_token(self):
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                return json.load(f).get("token")
        except (OSError, ValueError):
            return None

    def _save_token(self, token):
        try:
            with open(self.token_path, "w", encoding="utf-8") as f:
                json.dump({"token": token}, f)
        except OSError as e:
            log.warning("Could not save token: %s", e)

    def _forget_token(self):
        try:
            os.remove(self.token_path)
        except OSError:
            pass

    def _status(self, text):
        log.info(text)
        if self.on_status:
            self.on_status(text)

    # ---------- connection loop ----------
    async def run_forever(self):
        delay = 1
        while True:
            stop = False
            try:
                stop = await self._session()
                delay = 1
            except (OSError, websockets.exceptions.WebSocketException) as e:
                log.debug("Connection problem: %s", e)
            finally:
                self.connected.clear()
                self.ws = None
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(ApiError("disconnected", "Lost connection to Pureplay"))
                self._pending.clear()
            if stop:
                self._status("Pureplay refused the connection. Fix it in Settings > Accessories, "
                             "then restart Tiger.")
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 8)

    async def _session(self):
        """One socket lifetime. Returns True if we should stop retrying."""
        async with websockets.connect(self.uri, subprotocols=["binary"],
                                      open_timeout=5, ping_interval=20, max_size=None) as ws:
            self.ws = ws
            await self._send({"type": "pair", "data": {"client": self.client_name,
                                                        "version": "1.0",
                                                        "token": self._load_token()}})
            code = None
            try:
                async for raw in ws:
                    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
                    try:
                        msg = json.loads(text)
                    except ValueError:
                        log.warning("Unparseable message: %r", text[:200])
                        continue
                    await self._handle(msg)
            except websockets.exceptions.ConnectionClosed as e:
                code = e.rcvd.code if e.rcvd else None
            if code is None:
                code = ws.close_code
        log.info("Socket closed (code %s)", code)
        if code == 4401:
            self._forget_token()
            self._status("Pureplay removed Tiger's pairing. It will ask for approval again.")
        elif code == 4403:
            return True
        elif code == 4408:
            self._status("Approval timed out in Pureplay. Trying again.")
        elif code == 4429:
            await asyncio.sleep(120)
        return False

    async def _handle(self, msg):
        mtype = msg.get("type")
        data = msg.get("data") or {}

        if mtype == "hello":
            sid = data.get("serverInstanceId")
            if self._server_instance and sid != self._server_instance:
                log.info("Pureplay restarted")
            self._server_instance = sid
            if data.get("version") != 1:
                log.warning("Pureplay API version %s; Tiger was built for version 1", data.get("version"))

        elif mtype == "pairing.pending":
            self._status("Approve 'Tiger Voice Control' on the Pureplay screen (60 seconds).")

        elif mtype == "paired":
            self._save_token(data.get("token"))
            self.scopes = data.get("scopes") or []
            await self._send({"type": "subscribe", "id": "sub",
                              "data": {"events": self.SUBSCRIBE_EVENTS, "snapshot": False}})
            self.connected.set()
            if "control" in self.scopes:
                self._status("Connected to Pureplay with aim and club control.")
            else:
                self._status("Connected to Pureplay READ-ONLY, so Tiger can't change aim or club.\n"
                             "        To fix: in Pureplay > Settings > Accessories, click Remove next to "
                             "Tiger Voice Control,\n"
                             "        close Tiger, delete token.json in the Tiger folder, start Tiger again, "
                             "and choose\n"
                             "        'Aim and club' before clicking Allow.")

        elif mtype == "response":
            rid = msg.get("id")
            fut = self._pending.pop(rid, None) if rid else None
            if msg.get("ok"):
                if fut and not fut.done():
                    fut.set_result(data)
            else:
                err = msg.get("error") or {}
                exc = ApiError(err.get("code", "error"), err.get("message", ""), err.get("blockers"))
                if fut and not fut.done():
                    fut.set_exception(exc)
                else:
                    log.info("Pureplay: %s", exc)

        elif mtype == "event":
            name = msg.get("event")
            req = msg.get("requestId")
            if name == "state.snapshot" and req in self._pending:
                fut = self._pending.pop(req)
                if not fut.done():
                    fut.set_result(data)
            elif self.on_event:
                # Run handlers as tasks: they may call snapshot(), whose reply arrives on this
                # same read loop, so awaiting them here would deadlock.
                task = asyncio.create_task(self._run_handler(name, data))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        return False

    async def _run_handler(self, name, data):
        try:
            await self.on_event(name, data)
        except Exception:   # never let a handler kill the socket
            log.exception("Event handler failed for %s", name)

    async def _send(self, obj):
        if not self.ws:
            raise ApiError("disconnected", "Not connected to Pureplay")
        await self.ws.send(json.dumps(obj))

    async def _request(self, obj, timeout=3.0):
        rid = f"t{next(self._ids)}"
        obj["id"] = rid
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        try:
            await self._send(obj)
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(rid, None)

    # ---------- public API ----------
    @property
    def is_read_only(self):
        """Paired, but Pureplay granted read-only (no aim/club control)."""
        return self.connected.is_set() and "control" not in self.scopes

    @property
    def has_control(self):
        return self.connected.is_set() and "control" in self.scopes

    async def snapshot(self):
        if not self.connected.is_set():
            raise ApiError("disconnected", "Not connected to Pureplay")
        return await self._request({"type": "state.get"})

    async def command(self, name, **data):
        if not self.connected.is_set():
            raise ApiError("disconnected", "Not connected to Pureplay")
        for attempt in range(3):
            try:
                return await self._request({"type": "command", "command": name, "data": data})
            except ApiError as e:
                if e.code == "rate_limited" and attempt < 2:
                    await asyncio.sleep(0.1)
                    continue
                raise
