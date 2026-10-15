"""Exclusive, bounded RCP preflight. Never run it while Zigbee2MQTT owns the radio."""
from __future__ import annotations

from dataclasses import dataclass
import re
import socket
import time


@dataclass(frozen=True)
class Snapshot:
    boot_id: str
    runtime_id: str
    port: int
    connections: int


def snapshot_command() -> str:
    # No UART reads, writes, resets or TCP connections. The existing status
    # script reads config/GPIO/netstat only. MQTT IO is intentionally NOT a
    # prerequisite: older coordinator boots start it after the first TCP client.
    return """(
echo M1S_READY_BEGIN
if [ -x /data/m1s_coordinator/coordinator_status.sh ]; then
 /data/m1s_coordinator/coordinator_status.sh
fi
printf 'boot_id='; cat /proc/sys/kernel/random/boot_id
n=0; stock=0; owner=0
for d in /proc/[0-9]*; do
 read -r c < "$d/comm" 2>/dev/null || continue
 case "$c" in
 uart_tcp_relay*)
  n=$((n + 1))
  printf 'relay_id='; printf '%s:' "${d##*/}"; awk '{print $22}' "$d/stat"
  for f in "$d"/fd/*; do
   [ "$(readlink "$f" 2>/dev/null)" != /dev/ttyS1 ] || owner=1
  done;;
 mzigbee_agent) stock=1;;
 esac
done
echo "relays=$n"; echo "uart_owner=$owner"; echo "stock=$stock"
echo M1S_SOCKETS_BEGIN; netstat -ant 2>/dev/null; echo M1S_SOCKETS_END
echo M1S_READY_END
)"""


def parse_snapshot(output: str, expected_port: int) -> Snapshot:
    match = re.search(r"(?ms)^M1S_READY_BEGIN\r?\n(.*?)^M1S_READY_END\r?$", output)
    if not match:
        raise RuntimeError("readiness_response_incomplete")
    block = match.group(1)
    fields = {}
    for line in block.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep:
            if key in fields:
                raise RuntimeError("readiness_duplicate_field")
            fields[key] = value
    expected = {"role": "coordinator", "state": "ON", "enabled": "1",
                "gpio33": "1", "gpio18": "0", "relays": "1",
                "uart_owner": "1", "stock": "0", "port": str(expected_port)}
    for key, value in expected.items():
        if fields.get(key) != value:
            raise RuntimeError(f"coordinator_not_ready:{key}")
    boot_id = fields.get("boot_id", "")
    relay_id = fields.get("relay_id", "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", boot_id) or not re.fullmatch(r"\d+:\d+", relay_id):
        raise RuntimeError("runtime_identity_missing")
    sockets = re.search(r"(?ms)^M1S_SOCKETS_BEGIN\r?\n(.*?)^M1S_SOCKETS_END\r?$", block)
    if not sockets or "Local Address" not in sockets.group(1):
        raise RuntimeError("socket_status_missing")
    listening = False
    connections = 0
    for line in sockets.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0] in {"tcp", "tcp6"} and parts[3].rsplit(":", 1)[-1] == str(expected_port):
            listening |= parts[5] == "LISTEN"
            connections += parts[5] == "ESTABLISHED"
    if not listening:
        raise RuntimeError("relay_not_listening")
    return Snapshot(boot_id, f"{boot_id}:{relay_id}", expected_port, connections)


def isolated_command(client, command: str, timeout: float = 8) -> str:
    isolated = type(client)(host=client.host, port=client.port,
                            username=client.username, password=client.password, timeout=timeout)
    try:
        return isolated.run_command(command, timeout=timeout, connect_timeout=2)
    finally:
        isolated.disconnect()


def read_snapshot(client, port: int) -> Snapshot:
    return parse_snapshot(isolated_command(client, snapshot_command()), port)


def restart_runtime(client) -> None:
    # Mirrors the successful manual sequence, but resets only the existing RCP
    # runtime, after Supervisor confirms Z2M is stopped. No flash/network reset.
    output = isolated_command(client,
        "/data/m1s_coordinator/coordinator_on.sh", timeout=15)
    if not re.search(r"(?m)^COORDINATOR_ON_OK port=\d+\r?$", output):
        raise RuntimeError("coordinator_restart_not_acknowledged")


def packed(value: int) -> bytes:
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def unpack(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    for shift in range(0, 35, 7):
        if offset >= len(data):
            break
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise RuntimeError("invalid_spinel_integer")


def fcs(data: bytes) -> int:
    crc = 0xffff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc


def hdlc(data: bytes) -> bytes:
    checksum = fcs(data) ^ 0xffff
    payload = data + checksum.to_bytes(2, "little")
    result = bytearray(b"\x7e")
    for byte in payload:
        if byte in {0x7e, 0x7d, 0x11, 0x13, 0xf8}:
            result.extend((0x7d, byte ^ 0x20))
        else:
            result.append(byte)
    return bytes(result) + b"\x7e"


class Frames:
    def __init__(self):
        self.buffer = bytearray()
        self.escape = False

    def feed(self, data: bytes):
        frames = []
        for byte in data:
            if byte == 0x7e:
                if not self.escape and len(self.buffer) >= 4 and fcs(self.buffer) == 0xf0b8:
                    frames.append(bytes(self.buffer[:-2]))
                self.buffer.clear()
                self.escape = False
            elif byte == 0x7d:
                self.escape = True
            else:
                self.buffer.append(byte ^ 0x20 if self.escape else byte)
                self.escape = False
                if len(self.buffer) > 4096:
                    raise RuntimeError("oversized_spinel_frame")
        return frames


def probe_rcp(host: str, port: int, timeout: float = 8) -> dict:
    """Verify firmware AND PHY enable/disable on one exclusive TCP session.

    This is a host/RCP initialization test, not proof of over-air RX/TX. No
    network keys, PAN IDs, security counters, channels or device tables are set.
    """
    deadline = time.monotonic() + timeout
    decoder = Frames()
    tid = 0
    with socket.create_connection((host, port), timeout=min(2, timeout)) as conn:
        def request(prop: int, value: bytes | None = None) -> bytes:
            nonlocal tid
            tid = tid % 15 + 1
            header = 0x80 | tid
            conn.settimeout(max(0.01, deadline - time.monotonic()))
            conn.sendall(hdlc(bytes((header, 2 if value is None else 3)) + packed(prop) + (value or b"")))
            while time.monotonic() < deadline:
                conn.settimeout(max(0.01, deadline - time.monotonic()))
                chunk = conn.recv(2048)
                if not chunk:
                    raise RuntimeError("rcp_connection_closed")
                for frame in decoder.feed(chunk):
                    if frame[0] != header:
                        continue
                    command, offset = unpack(frame, 1)
                    key, offset = unpack(frame, offset)
                    if command != 6:
                        continue
                    if key == prop:
                        return frame[offset:]
                    if key == 0:
                        status, _ = unpack(frame, offset)
                        raise RuntimeError(f"rcp_status:{status}")
            raise RuntimeError("rcp_probe_timeout")

        protocol = request(1)
        major, offset = unpack(protocol)
        minor, end = unpack(protocol, offset)
        if end != len(protocol) or (major, minor) != (4, 3):
            raise RuntimeError("unexpected_rcp_protocol")
        firmware = request(2).rstrip(b"\x00").decode("utf-8", errors="strict")
        if "JN_5189" not in firmware or "M1S_IO_V2" not in firmware:
            raise RuntimeError("unexpected_rcp_firmware")
        interface, _ = unpack(request(3))
        if interface != 3:
            raise RuntimeError("unexpected_rcp_interface")
        try:
            if request(0x20, b"\x01") != b"\x01" or request(0x20) != b"\x01":
                raise RuntimeError("rcp_phy_enable_failed")
        finally:
            # Leave the radio disabled for Zigbee2MQTT to initialize itself.
            if request(0x20, b"\x00") != b"\x00":
                raise RuntimeError("rcp_phy_disable_failed")
        return {"protocol": f"{major}.{minor}", "firmware": firmware, "phy_test": "passed"}
