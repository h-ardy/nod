"""Stand-in for the `bleak` package used only in tests: 'Bluetooth' is a TCP socket to the firmware simulator.

Addresses look like 127.0.0.1:47910. Devices for BleakScanner come from NOD_FAKE_DEVICES,
a comma list of NAME@HOST:PORT.
"""
import asyncio
import os


class BLEDevice:
    def __init__(self, name, address):
        self.name, self.address = name, address


class BleakScanner:
    @staticmethod
    async def discover(timeout=5.0):
        out = []
        for item in filter(None, os.environ.get("NOD_FAKE_DEVICES", "").split(",")):
            name, addr = item.split("@")
            out.append(BLEDevice(name, addr))
        return out


class BleakClient:
    def __init__(self, address_or_device, **_):
        self.address = getattr(address_or_device, "address", address_or_device)
        self._r = self._w = None
        self._task = None

    @property
    def is_connected(self):
        return self._w is not None and not self._w.is_closing() and not (self._r and self._r.at_eof())

    async def connect(self):
        host, port = self.address.rsplit(":", 1)
        self._r, self._w = await asyncio.open_connection(host, int(port))
        return True

    async def disconnect(self):
        if self._task:
            self._task.cancel()
        if self._w:
            self._w.close()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()

    async def start_notify(self, _uuid, callback):
        async def pump():
            while True:
                data = await self._r.read(244)
                if not data:
                    return
                callback(None, bytearray(data))
        self._task = asyncio.ensure_future(pump())

    async def write_gatt_char(self, _uuid, data, response=False):
        if len(data) > 20:
            raise ValueError("write longer than the default ATT MTU payload")
        self._w.write(bytes(data))
        await self._w.drain()
