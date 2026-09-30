"""Strict client for the Coordinator relay sideband channel."""
import json

RELAY = "/data/m1s_coordinator/bin/uart_tcp_relay_mipsel"


def request(client, operation: str, values=()):
    """Run one validated sideband operation without touching the Spinel port."""
    if operation not in {"capabilities", "state", "rgb", "lux-start", "lux-get"}:
        raise ValueError("Unsupported coordinator operation")
    if operation == "rgb":
        if len(values) != 3 or any(
            type(value) is not int or not 0 <= value <= 255 for value in values
        ):
            raise ValueError("RGB must contain three bytes")
    elif values:
        raise ValueError("Unexpected coordinator arguments")

    command = f"{RELAY} --io {operation}" + "".join(f" {value}" for value in values)
    output = client.run_command(command, timeout=4.0)
    lines = [line.strip() for line in output.splitlines() if line.strip().startswith("{")]
    if len(lines) != 1:
        raise RuntimeError("Coordinator IO helper unavailable")

    result = json.loads(lines[0])
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError("Coordinator IO request failed")
    if (
        type(result.get("version")) is not int
        or result["version"] != 1
        or result.get("capabilities") != 3
    ):
        raise RuntimeError("Unsupported coordinator IO protocol")

    rgb = result.get("rgb")
    if (
        not isinstance(rgb, list)
        or len(rgb) != 3
        or any(type(value) is not int or not 0 <= value <= 255 for value in rgb)
    ):
        raise RuntimeError("Invalid coordinator RGB state")
    if type(result.get("valid")) is not bool:
        raise RuntimeError("Invalid lux validity")
    for key, limit in (("raw", 4095), ("millivolts", 3600), ("lux", 65535)):
        if type(result.get(key)) is not int or not 0 <= result[key] <= limit:
            raise RuntimeError("Invalid coordinator lux state")
    return result
