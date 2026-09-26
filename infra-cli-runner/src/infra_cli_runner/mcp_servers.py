"""Hosted stdio MCP servers: baked packages run as long-lived processes behind a Streamable HTTP façade."""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import os
import shutil
import signal
import time
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.infra_cli_runner.models import (
    HostedMCPPackage,
    HostedMCPServerSpec,
    HostedMCPServerState,
    HostedMCPServerStatus,
)
from src.infra_cli_runner.service import BASE_ENV

log = logging.getLogger(__name__)

# In the image: /app/mcp_packages (definitions) and /opt/mcp/<key> (venvs built at image build time).
DEFAULT_PACKAGES_ROOT = Path(__file__).resolve().parents[2] / "mcp_packages"
DEFAULT_VENV_ROOT = Path("/opt/mcp")
DEFAULT_SERVERS_ROOT = Path("/tmp/infra-cli-runner/mcp")

MCP_PROTOCOL_VERSION = "2025-06-18"
STARTUP_TIMEOUT_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 120
DRAIN_TIMEOUT_SECONDS = 30
STOP_GRACE_SECONDS = 5
IDLE_TIMEOUT_SECONDS = 15 * 60
REAP_INTERVAL_SECONDS = 60
# Each Python server holds ~100 MB; sized for the current Railway plan.
MAX_RUNNING_SERVERS = 8
# asyncio's 64 KiB StreamReader default truncates real tools/list results.
MAX_MESSAGE_BYTES = 8 * 1024 * 1024
STDERR_TAIL_BYTES = 16 * 1024

INITIALIZE_PARAMS = {
    "protocolVersion": MCP_PROTOCOL_VERSION,
    "capabilities": {},
    "clientInfo": {"name": "innomightlabs", "title": "InnoMight Labs", "version": "1.0.0"},
}
METHOD_NOT_SUPPORTED = -32601


class HostedMCPError(Exception):
    """Base class for hosted MCP server failures the router maps to HTTP statuses."""


class UnknownPackageError(HostedMCPError, ValueError):
    pass


class ServerNotRunningError(HostedMCPError):
    pass


class PoolFullError(HostedMCPError):
    pass


class ServerRequestTimeout(HostedMCPError):
    pass


@dataclass(frozen=True)
class MCPPackage:
    key: str
    entrypoint: str
    args: tuple[str, ...]
    command: Path

    def to_response(self) -> HostedMCPPackage:
        return HostedMCPPackage(key=self.key, entrypoint=self.entrypoint, installed=self.command.exists())


def load_packages(packages_root: Path, venv_root: Path) -> dict[str, MCPPackage]:
    """Read mcp_packages/<key>/package.toml. The directory name is the key; the venv lives at venv_root/<key>."""
    packages: dict[str, MCPPackage] = {}
    if not packages_root.is_dir():
        return packages
    for definition in sorted(packages_root.glob("*/package.toml")):
        key = definition.parent.name
        data = tomllib.loads(definition.read_text(encoding="utf-8"))
        entrypoint = str(data["entrypoint"])
        packages[key] = MCPPackage(
            key=key,
            entrypoint=entrypoint,
            args=tuple(str(arg) for arg in data.get("args", [])),
            command=venv_root / key / "bin" / entrypoint,
        )
    return packages


class StdioMCPServer:
    """One stdio MCP process and the JSON-RPC multiplexer in front of it."""

    def __init__(self, server_id: str, spec: HostedMCPServerSpec, package: MCPPackage, directory: Path):
        self.server_id = server_id
        self.spec = spec
        self.fingerprint = spec.fingerprint()
        self.package = package
        self.directory = directory
        self.state: HostedMCPServerState = "starting"
        self.error: str | None = None
        self.exit_code: int | None = None
        self.initialize_result: dict[str, Any] | None = None
        self.started_at: datetime | None = None
        self.last_used_at: datetime | None = None
        self.last_used_monotonic = time.monotonic()
        self.in_flight = 0
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._ids = itertools.count(1)
        self._write_lock = asyncio.Lock()
        self._stderr_tail = bytearray()
        self._tasks: list[asyncio.Task[None]] = []
        self._startup: asyncio.Task[None] | None = None

    @property
    def home(self) -> Path:
        return self.directory / "home"

    @property
    def secrets(self) -> Path:
        return self.directory / "secrets"

    def begin(self) -> None:
        self._startup = asyncio.create_task(self._start())

    async def wait_settled(self, timeout: float) -> None:
        """Wait until running or failed, without cancelling a start that outlives the wait."""
        if self._startup is not None and timeout > 0:
            await asyncio.wait({self._startup}, timeout=timeout)

    async def forward(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Send one JSON-RPC message from a caller; return the response for requests, None for notifications."""
        if self.state != "running":
            raise ServerNotRunningError("MCP server is not running")
        self.touch()
        if "id" not in message:
            await self._write(message)
            return None

        self.in_flight += 1
        try:
            # Concurrent callers may reuse ids, so the child only ever sees ids we allocate.
            response = await self._request_raw({**message, "id": None}, timeout=REQUEST_TIMEOUT_SECONDS)
        finally:
            self.in_flight -= 1
            self.touch()
        return {**response, "id": message["id"]}

    async def drain(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while self.in_flight and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

    async def stop(self) -> None:
        if self.state in ("starting", "running"):
            self.state = "stopped"
        if self._startup is not None and not self._startup.done():
            self._startup.cancel()
        await self._terminate()
        for task in self._tasks:
            task.cancel()
        self._fail_pending("MCP server stopped")
        shutil.rmtree(self.secrets, ignore_errors=True)

    def status(self) -> HostedMCPServerStatus:
        server_info = (self.initialize_result or {}).get("serverInfo")
        return HostedMCPServerStatus(
            server_id=self.server_id,
            package=self.package.key,
            state=self.state,
            started_at=self.started_at,
            last_used_at=self.last_used_at,
            exit_code=self.exit_code,
            error=self.error,
            stderr_tail=self._stderr_tail.decode("utf-8", errors="replace"),
            server_info=server_info if isinstance(server_info, dict) else None,
        )

    def cached_initialize(self, request_id: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": self.initialize_result or {}}

    async def _start(self) -> None:
        try:
            self._process = await asyncio.create_subprocess_exec(
                str(self.package.command),
                *self.package.args,
                *self.spec.args,
                cwd=self.home,
                env=self._environment(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Its own process group, so stop() also reaches any children the server spawns.
                start_new_session=True,
                limit=MAX_MESSAGE_BYTES,
            )
            self._tasks = [
                asyncio.create_task(self._read_messages()),
                asyncio.create_task(self._read_stderr()),
            ]
            response = await self._request_raw(
                {"jsonrpc": "2.0", "id": None, "method": "initialize", "params": INITIALIZE_PARAMS},
                timeout=STARTUP_TIMEOUT_SECONDS,
            )
            if "error" in response or not isinstance(response.get("result"), dict):
                raise HostedMCPError(f"MCP initialize failed: {json.dumps(response.get('error'))}")
            self.initialize_result = response["result"]
            await self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self.state = "running"
            self.started_at = datetime.now(timezone.utc)
            self.touch()
            log.info("Hosted MCP server running server_id=%s package=%s", self.server_id, self.package.key)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self.state == "starting":
                self.state = "failed"
                self.error = self.error or _describe(exc)
            log.warning("Hosted MCP server failed to start server_id=%s error=%s", self.server_id, self.error)
            await self._terminate()

    def _environment(self) -> dict[str, str]:
        self.home.mkdir(parents=True, exist_ok=True)
        env = dict(BASE_ENV)
        env.update(
            {
                "HOME": str(self.home),
                "TMPDIR": str(self.home),
                "XDG_CACHE_HOME": str(self.home / ".cache"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "XDG_DATA_HOME": str(self.home / ".local" / "share"),
                "PATH": f"{self.package.command.parent}:{BASE_ENV['PATH']}",
                "PYTHONUNBUFFERED": "1",
            }
        )
        env.update(self.spec.env)
        if self.spec.files:
            self.secrets.mkdir(mode=0o700, parents=True, exist_ok=True)
            for name, content in self.spec.files.items():
                path = self.secrets / name
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(content)
                env[name] = str(path)
        return env

    async def _request_raw(self, message: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        internal_id = next(self._ids)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[internal_id] = future
        try:
            await self._write({**message, "id": internal_id})
            return await asyncio.wait_for(future, timeout)
        except TimeoutError as exc:
            await self._cancel_remote(internal_id)
            raise ServerRequestTimeout(f"MCP server did not answer within {int(timeout)}s") from exc
        finally:
            self._pending.pop(internal_id, None)

    async def _cancel_remote(self, internal_id: int) -> None:
        try:
            await self._write(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": internal_id, "reason": "timeout"},
                }
            )
        except (HostedMCPError, ConnectionError):
            pass

    async def _write(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            raise ServerNotRunningError("MCP server is not running")
        frame = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            process.stdin.write(frame)
            await process.stdin.drain()

    async def _read_messages(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            while line := await self._process.stdout.readline():
                message = _decode_line(line)
                if message is None:
                    continue
                if "method" in message:
                    # We declare no client capabilities, so server-to-client requests (sampling, roots,
                    # elicitation) are refused; server notifications (logging, progress) are dropped.
                    if "id" in message:
                        await self._write(
                            {
                                "jsonrpc": "2.0",
                                "id": message["id"],
                                "error": {"code": METHOD_NOT_SUPPORTED, "message": "Not supported by InnoMight Labs"},
                            }
                        )
                    continue
                future = self._pending.get(message.get("id"))  # type: ignore[arg-type]
                if future is not None and not future.done():
                    future.set_result(message)
        except (ValueError, asyncio.LimitOverrunError):
            self.error = f"MCP server sent a message larger than {MAX_MESSAGE_BYTES} bytes"
            await self._terminate()
        except (HostedMCPError, ConnectionError):
            pass
        finally:
            await self._mark_exited()

    async def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        while chunk := await self._process.stderr.read(4096):
            self._stderr_tail.extend(chunk)
            del self._stderr_tail[:-STDERR_TAIL_BYTES]

    async def _mark_exited(self) -> None:
        if self._process is not None:
            self.exit_code = await self._process.wait()
        if self.state in ("starting", "running"):
            self.state = "failed"
            self.error = self.error or f"MCP server exited with code {self.exit_code}"
            log.warning("Hosted MCP server exited server_id=%s code=%s", self.server_id, self.exit_code)
        self._fail_pending(self.error or "MCP server exited")

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ServerNotRunningError(reason))

    async def _terminate(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        if process.stdin is not None:
            process.stdin.close()
        _signal_group(process, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), STOP_GRACE_SECONDS)
        except TimeoutError:
            _signal_group(process, signal.SIGKILL)
            await process.wait()

    def touch(self) -> None:
        self.last_used_monotonic = time.monotonic()
        self.last_used_at = datetime.now(timezone.utc)


class StdioMCPServerPool:
    """All hosted servers in this process. The runner therefore runs as one replica with one worker."""

    def __init__(
        self,
        *,
        packages_root: Path = DEFAULT_PACKAGES_ROOT,
        venv_root: Path = DEFAULT_VENV_ROOT,
        servers_root: Path = DEFAULT_SERVERS_ROOT,
        max_running: int = MAX_RUNNING_SERVERS,
        idle_timeout_seconds: float = IDLE_TIMEOUT_SECONDS,
    ):
        self.packages = load_packages(packages_root, venv_root)
        self.servers_root = servers_root
        self.max_running = max_running
        self.idle_timeout_seconds = idle_timeout_seconds
        self._servers: dict[str, StdioMCPServer] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def list_packages(self) -> list[HostedMCPPackage]:
        return [package.to_response() for package in self.packages.values()]

    async def ensure(self, server_id: str, spec: HostedMCPServerSpec, *, wait_seconds: float) -> HostedMCPServerStatus:
        package = self.packages.get(spec.package)
        if package is None:
            raise UnknownPackageError(f"Unknown MCP package: {spec.package}")

        async with self._locks[server_id]:
            server = self._servers.get(server_id)
            reusable = (
                server is not None
                and server.fingerprint == spec.fingerprint()
                and server.state in ("starting", "running")
            )
            if not reusable:
                if server is not None:
                    # New credentials or config: let in-flight calls finish, then replace the process.
                    await server.drain(DRAIN_TIMEOUT_SECONDS)
                    await server.stop()
                    self._servers.pop(server_id, None)
                await self._make_room()
                server = StdioMCPServer(server_id, spec, package, self.servers_root / server_id)
                self._servers[server_id] = server
                server.begin()
                log.info("Starting hosted MCP server server_id=%s package=%s", server_id, package.key)

        assert server is not None
        await server.wait_settled(wait_seconds)
        return server.status()

    def status(self, server_id: str) -> HostedMCPServerStatus | None:
        server = self._servers.get(server_id)
        return server.status() if server else None

    async def forward(self, server_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
        server = self._servers.get(server_id)
        if server is None:
            raise ServerNotRunningError("MCP server is not running")
        if message.get("method") == "initialize":
            # One stdio process serves many HTTP sessions and accepts a single handshake, done at start.
            if server.state != "running":
                raise ServerNotRunningError("MCP server is not running")
            server.touch()
            return server.cached_initialize(message.get("id"))
        if message.get("method") == "notifications/initialized":
            return None
        return await server.forward(message)

    async def delete(self, server_id: str) -> None:
        async with self._locks[server_id]:
            server = self._servers.pop(server_id, None)
            if server is not None:
                await server.stop()
            shutil.rmtree(self.servers_root / server_id, ignore_errors=True)

    async def reap_idle(self) -> None:
        now = time.monotonic()
        for server_id, server in list(self._servers.items()):
            idle = now - server.last_used_monotonic
            # Failed servers are cleared after a minute so their status stays visible briefly, then frees the slot.
            expired = idle >= self.idle_timeout_seconds or (server.state == "failed" and idle >= 60)
            if server.in_flight == 0 and expired:
                async with self._locks[server_id]:
                    if self._servers.get(server_id) is server:
                        log.info("Stopping idle hosted MCP server server_id=%s state=%s", server_id, server.state)
                        await server.stop()
                        self._servers.pop(server_id, None)

    async def run_reaper(self) -> None:
        while True:
            await asyncio.sleep(REAP_INTERVAL_SECONDS)
            try:
                await self.reap_idle()
            except Exception:
                log.exception("Hosted MCP idle reaper failed")

    async def close(self) -> None:
        for server_id in list(self._servers):
            server = self._servers.pop(server_id)
            await server.stop()

    async def _make_room(self) -> None:
        active = [server for server in self._servers.values() if server.state in ("starting", "running")]
        if len(active) < self.max_running:
            return
        idle = [server for server in active if server.in_flight == 0]
        if not idle:
            raise PoolFullError("All hosted MCP server slots are busy. Try again shortly.")
        victim = min(idle, key=lambda server: server.last_used_monotonic)
        log.info("Evicting least recently used hosted MCP server server_id=%s", victim.server_id)
        await victim.stop()
        self._servers.pop(victim.server_id, None)


def _decode_line(line: bytes) -> dict[str, Any] | None:
    text = line.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        # Some servers print banners on stdout; they are not protocol messages.
        log.info("Ignoring non-JSON line from hosted MCP server: %s", text[:200])
        return None
    return message if isinstance(message, dict) else None


def _describe(exc: BaseException) -> str:
    message = str(exc) or type(exc).__name__
    return message if isinstance(exc, HostedMCPError) else f"{type(exc).__name__}: {message}"


def _signal_group(process: asyncio.subprocess.Process, sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
    except OSError:
        process.send_signal(sig)


_pool: StdioMCPServerPool | None = None


def get_mcp_server_pool() -> StdioMCPServerPool:
    global _pool
    if _pool is None:
        _pool = StdioMCPServerPool()
    return _pool
