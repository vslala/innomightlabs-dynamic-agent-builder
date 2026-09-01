from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


_WRITE_ROOT_VALUE = os.environ.get("INFRA_CLI_RUNNER_WRITE_ROOT", "")
if not _WRITE_ROOT_VALUE:
    raise RuntimeError("Python runner write policy is not configured")

WRITE_ROOT = Path(_WRITE_ROOT_VALUE).resolve()
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
BLOCKED_PROCESS_EVENTS = {
    "os.exec",
    "os.fork",
    "os.forkpty",
    "os.posix_spawn",
    "os.spawn",
    "os.system",
    "pty.spawn",
    "subprocess.Popen",
}
SINGLE_PATH_WRITE_EVENTS = {
    "os.chmod",
    "os.chown",
    "os.mkdir",
    "os.remove",
    "os.rmdir",
    "os.truncate",
    "os.unlink",
    "os.utime",
}
TWO_PATH_WRITE_EVENTS = {"os.link", "os.rename"}
DIR_FD_ARGUMENTS = {
    "os.chmod": (2,),
    "os.chown": (3,),
    "os.link": (2, 3),
    "os.mkdir": (2,),
    "os.remove": (1,),
    "os.rename": (2, 3),
    "os.rmdir": (1,),
    "os.symlink": (2,),
    "os.unlink": (1,),
    "os.utime": (3,),
}


def _require_managed_path(value: Any) -> None:
    if isinstance(value, int):
        return
    try:
        path = Path(os.fsdecode(value))
    except TypeError as exc:
        raise PermissionError("Write path is not a filesystem path") from exc
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path.resolve(strict=False).relative_to(WRITE_ROOT)
    except ValueError as exc:
        raise PermissionError(f"Writes are restricted to {WRITE_ROOT}") from exc


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event == "import" and args and args[0] == "_posixsubprocess":
        raise PermissionError("Low-level process execution is not allowed in Python scripts")
    if event == "open":
        path, mode, flags = args
        writes = bool(flags & WRITE_FLAGS) if isinstance(flags, int) else False
        writes = writes or (isinstance(mode, str) and any(token in mode for token in "wax+"))
        if writes:
            if mode is None and not Path(os.fsdecode(path)).is_absolute():
                raise PermissionError("Relative low-level writes are not allowed")
            _require_managed_path(path)
        return
    for argument_index in DIR_FD_ARGUMENTS.get(event, ()):
        if len(args) > argument_index and args[argument_index] not in (None, -1):
            raise PermissionError("Directory-relative writes are not allowed")
    if event in SINGLE_PATH_WRITE_EVENTS:
        _require_managed_path(args[0])
        return
    if event in TWO_PATH_WRITE_EVENTS:
        _require_managed_path(args[0])
        _require_managed_path(args[1])
        return
    if event == "os.symlink":
        _require_managed_path(args[1])
        return
    if event in BLOCKED_PROCESS_EVENTS:
        raise PermissionError("Child process execution is not allowed in Python scripts")
    if event in {"ctypes.dlopen", "ctypes.dlsym", "ctypes.dlsym/handle"}:
        raise PermissionError("Native library loading is not allowed in Python scripts")


sys.addaudithook(_audit)
