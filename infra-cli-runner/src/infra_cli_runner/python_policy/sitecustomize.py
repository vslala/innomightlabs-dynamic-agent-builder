from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


_WRITE_ROOT_VALUE = os.environ.get("INFRA_CLI_RUNNER_WRITE_ROOT", "")
if not _WRITE_ROOT_VALUE:
    raise RuntimeError("Python runner write policy is not configured")

WRITE_ROOT = Path(_WRITE_ROOT_VALUE).resolve()
_BROWSER_VENV_VALUE = os.environ.get("INFRA_CLI_RUNNER_BROWSER_VENV", "")
BROWSER_VENV = Path(_BROWSER_VENV_VALUE).resolve() if _BROWSER_VENV_VALUE else None
# Resolve candidates before scripts can mutate their environment or import search path.
BROWSER_NODES = frozenset(
    path.absolute()
    for path in BROWSER_VENV.glob("lib/python*/site-packages/playwright/driver/node")
    if path.resolve() == path.absolute() and path.is_file()
) if BROWSER_VENV else frozenset()
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
        resolved = path.resolve(strict=False)
        resolved.relative_to(WRITE_ROOT)
        if BROWSER_VENV is not None:
            # Check both names: unlink/rename acts on the symlink, not its resolved target.
            lexical = Path(os.path.abspath(path))
            for candidate in (lexical, resolved):
                if (
                    candidate == BROWSER_VENV
                    or BROWSER_VENV in candidate.parents
                    or candidate in BROWSER_VENV.parents
                ):
                    raise PermissionError("Browser virtual environment is read-only")
    except ValueError as exc:
        raise PermissionError(f"Writes are restricted to {WRITE_ROOT}") from exc


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event == "import" and args and args[0] == "_posixsubprocess" and BROWSER_VENV is None:
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
    if event == "subprocess.Popen" and BROWSER_VENV is not None:
        executable = Path(os.fsdecode(args[0]))
        if executable.is_absolute() and executable in BROWSER_NODES and executable.resolve() == executable:
            return
    if event in BLOCKED_PROCESS_EVENTS:
        raise PermissionError("Child process execution is not allowed in Python scripts")


sys.addaudithook(_audit)
