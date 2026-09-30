"""Validated Coordinator sideband protocol over an isolated Telnet session."""
import json

HELPER = "/data/m1s_coordinator/coordinator_io.sh"


def request(client, operation: str, values=()) -> dict:
    """Execute one helper operation without using Router UART or Spinel."""
    if operation not in {"rgb", "lux-start", "lux-get"}:
        raise ValueError("Unsupported Coordinator sideband operation")
    if operation == "rgb":
        if len(values) != 3 or any(
            type(value) is not int or not 0 <= value <= 255 for value in values
        ):
            raise ValueError("RGB must contain three bytes")
    elif values:
        raise ValueError("Unexpected Coordinator sideband arguments")

    arguments = "".join(f" {value}" for value in values)
    output = client.run_isolated_command(
        f"test -x {HELPER} && {HELPER} {operation}{arguments}",
        timeout=4.0,
    )
    lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("{")
    ]
    if len(lines) != 1:
        raise RuntimeError("Coordinator sideband helper unavailable")

    result = json.loads(lines[0])
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError("Coordinator sideband request failed")
    if (
        type(result.get("version")) is not int
        or result["version"] != 1
        or result.get("capabilities") != 3
    ):
        raise RuntimeError("M1S_IO_V2 sideband capability not confirmed")

    rgb = result.get("rgb")
    if (
        not isinstance(rgb, list)
        or len(rgb) != 3
        or any(type(value) is not int or not 0 <= value <= 255 for value in rgb)
    ):
        raise RuntimeError("Invalid Coordinator RGB state")
    if type(result.get("valid")) is not bool:
        raise RuntimeError("Invalid Coordinator lux validity")
    for key, limit in (("raw", 4095), ("millivolts", 3600), ("lux", 65535)):
        if type(result.get(key)) is not int or not 0 <= result[key] <= limit:
            raise RuntimeError("Invalid Coordinator lux state")
    return result
