"""Select an external POSIX shell for local tests, not for hub execution."""
import os
from pathlib import Path


def shell_command(*args):
    busybox = os.environ.get("M1S_TEST_BUSYBOX")
    return [busybox, "sh", *args] if busybox else ["sh", *args]


def shell_path(path):
    value = Path(path).resolve().as_posix()
    if os.name == "nt" and not os.environ.get("M1S_TEST_BUSYBOX"):
        return "/" + value.replace(":", "", 1)
    return value
