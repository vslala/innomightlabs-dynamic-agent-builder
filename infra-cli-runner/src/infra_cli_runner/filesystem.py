from __future__ import annotations

import base64
import difflib
import fnmatch
import json
import os
import re
import shutil
import stat as stat_module
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from src.infra_cli_runner.models import FileSystemActionRequest, FileSystemActionResponse


DEFAULT_WORKSPACE_ROOT = Path(
    os.getenv("FILE_SYSTEM_WORKSPACE_ROOT", "/tmp/infra-cli-runner/workspaces")
)
DEFAULT_MAX_READ_BYTES = 64 * 1024
HARD_MAX_READ_BYTES = 256 * 1024
DEFAULT_MAX_READ_LINES = 500
HARD_MAX_READ_LINES = 2_000
DEFAULT_MAX_WRITE_BYTES = 2 * 1024 * 1024
DEFAULT_WORKSPACE_QUOTA_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_RESULTS = 100
HARD_MAX_RESULTS = 1_000
MAX_BATCH_OPERATIONS = 50
MAX_DIFF_BYTES = 128 * 1024
MAX_PATCH_BYTES = 512 * 1024
RESERVED_NAMES = {".runs"}
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
ACTION_ARGUMENTS = {
    "list_dir": {"path", "recursive", "max_depth", "limit"},
    "stat": {"path"},
    "search": {"path", "glob", "query", "max_results", "snippet_chars"},
    "read_chunk": {"path", "cursor", "byte_offset", "max_bytes", "start_line", "max_lines"},
    "write_file": {"path", "content", "mode"},
    "patch_file": {"path", "patch"},
    "preview_diff": {"path", "proposed_content", "patch"},
    "mkdir": {"path", "parents"},
    "copy": {"source", "destination", "overwrite"},
    "move": {"source", "destination", "overwrite"},
    "delete": {"path", "recursive"},
    "batch": {"operations", "continue_on_error"},
}


class FileSystemOperationError(Exception):
    def __init__(self, code: str, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.payload = payload or {}


class FileSystemService:
    def __init__(
        self,
        *,
        workspace_root: Path = DEFAULT_WORKSPACE_ROOT,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        max_write_bytes: int = DEFAULT_MAX_WRITE_BYTES,
        workspace_quota_bytes: int = DEFAULT_WORKSPACE_QUOTA_BYTES,
    ) -> None:
        self._workspace_root = workspace_root
        self._max_read_bytes = min(max(1024, max_read_bytes), HARD_MAX_READ_BYTES)
        self._max_write_bytes = max(1024, max_write_bytes)
        self._workspace_quota_bytes = max(self._max_write_bytes, workspace_quota_bytes)

    def execute(self, request: FileSystemActionRequest) -> FileSystemActionResponse:
        try:
            workspace = self.workspace(request.workspace_id)
            return self._dispatch(
                workspace,
                request.action,
                request.arguments,
                allow_batch=True,
            )
        except FileSystemOperationError as exc:
            return FileSystemActionResponse(
                status="error",
                payload=exc.payload,
                error_code=exc.code,
                message=exc.message,
            )
        except (OSError, UnicodeError) as exc:
            return FileSystemActionResponse(
                status="error",
                error_code="filesystem_error",
                message=str(exc),
            )

    def workspace(self, workspace_id: str) -> Path:
        root = self._workspace_root.resolve()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        workspace = (root / workspace_id).resolve()
        self._require_under(workspace, root)
        workspace.mkdir(mode=0o700, exist_ok=True)
        return workspace

    def _dispatch(
        self,
        workspace: Path,
        action: str,
        arguments: dict[str, Any],
        *,
        allow_batch: bool,
    ) -> FileSystemActionResponse:
        if not isinstance(arguments, dict):
            raise FileSystemOperationError("invalid_arguments", "arguments must be an object")
        allowed_arguments = ACTION_ARGUMENTS.get(action)
        if allowed_arguments is None:
            raise FileSystemOperationError("invalid_action", f"Unsupported filesystem action: {action}")
        unknown_arguments = sorted(set(arguments) - allowed_arguments)
        if unknown_arguments:
            raise FileSystemOperationError(
                "invalid_arguments",
                f"Unsupported arguments for {action}: {', '.join(unknown_arguments)}",
            )
        handlers = {
            "list_dir": self._list_dir,
            "stat": self._stat,
            "search": self._search,
            "read_chunk": self._read_chunk,
            "write_file": self._write_file,
            "patch_file": self._patch_file,
            "preview_diff": self._preview_diff,
            "mkdir": self._mkdir,
            "copy": self._copy,
            "move": self._move,
            "delete": self._delete,
        }
        if action == "batch":
            if not allow_batch:
                raise FileSystemOperationError("invalid_arguments", "nested batch operations are not allowed")
            return self._batch(workspace, arguments)
        handler = handlers.get(action)
        if handler is None:
            raise FileSystemOperationError("invalid_action", f"Unsupported filesystem action: {action}")
        return handler(workspace, arguments)

    def _list_dir(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        path = self._path(workspace, args.get("path", ""), allow_root=True)
        if not path.exists():
            raise FileSystemOperationError("not_found", "Directory does not exist")
        if not path.is_dir():
            raise FileSystemOperationError("not_directory", "Path is not a directory")
        recursive = self._bool(args, "recursive", False)
        max_depth = self._bounded_int(args.get("max_depth", 3), 1, 10, "max_depth")
        limit = self._bounded_int(args.get("limit", DEFAULT_MAX_RESULTS), 1, HARD_MAX_RESULTS, "limit")
        entries: list[dict[str, Any]] = []

        def visit(directory: Path, depth: int) -> None:
            for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
                if len(entries) >= limit:
                    return
                self._validate_existing_components(child, workspace)
                relative = child.relative_to(workspace).as_posix()
                if relative.split("/", 1)[0] in RESERVED_NAMES:
                    continue
                metadata = self._metadata(child, workspace)
                metadata["depth"] = depth
                entries.append(metadata)
                if recursive and child.is_dir() and not child.is_symlink() and depth < max_depth:
                    visit(child, depth + 1)

        visit(path, 1)
        return self._success(
            {"path": self._relative(path, workspace), "entries": entries, "truncated": len(entries) >= limit}
        )

    def _stat(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        path = self._path(workspace, self._required_str(args, "path"), allow_root=True)
        if not path.exists() and not path.is_symlink():
            raise FileSystemOperationError("not_found", "Path does not exist")
        return self._success(self._metadata(path, workspace))

    def _search(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        base = self._path(workspace, args.get("path", ""), allow_root=True)
        if not base.is_dir():
            raise FileSystemOperationError("not_directory", "Search path is not a directory")
        pattern = str(args.get("glob", "**/*"))
        if "\x00" in pattern or len(pattern) > 512:
            raise FileSystemOperationError("invalid_arguments", "glob is invalid")
        query_value = args.get("query")
        query = None if query_value is None else str(query_value)
        if query is not None and not query:
            raise FileSystemOperationError("invalid_arguments", "query must not be empty")
        max_results = self._bounded_int(args.get("max_results", DEFAULT_MAX_RESULTS), 1, HARD_MAX_RESULTS, "max_results")
        snippet_chars = self._bounded_int(args.get("snippet_chars", 240), 40, 1000, "snippet_chars")
        matches: list[dict[str, Any]] = []
        scanned = 0
        for candidate in sorted(base.rglob("*")):
            if len(matches) >= max_results:
                break
            if candidate.is_dir() or candidate.is_symlink():
                continue
            self._validate_existing_components(candidate, workspace)
            relative_base = candidate.relative_to(base).as_posix()
            if not self._matches_glob(relative_base, pattern):
                continue
            scanned += 1
            item: dict[str, Any] = {"path": self._relative(candidate, workspace), "size": candidate.stat().st_size}
            if query is not None:
                if self._is_binary(candidate):
                    continue
                found = self._find_text(candidate, query, snippet_chars)
                if found is None:
                    continue
                item.update(found)
            matches.append(item)
        return self._success({"matches": matches, "count": len(matches), "scanned": scanned, "truncated": len(matches) >= max_results})

    def _read_chunk(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        path_text = self._required_str(args, "path")
        path = self._path(workspace, path_text)
        self._require_regular_text_file(path)
        cursor = args.get("cursor")
        start_line = args.get("start_line")
        byte_offset = args.get("byte_offset", 0)
        if cursor is not None:
            if start_line is not None or args.get("byte_offset") is not None:
                raise FileSystemOperationError("invalid_arguments", "cursor cannot be combined with line or byte offsets")
            byte_offset = self._decode_cursor(str(cursor), self._relative(path, workspace))
        max_bytes = self._bounded_int(args.get("max_bytes", self._max_read_bytes), 1, self._max_read_bytes, "max_bytes")
        max_lines = self._bounded_int(args.get("max_lines", DEFAULT_MAX_READ_LINES), 1, HARD_MAX_READ_LINES, "max_lines")
        if start_line is not None:
            if args.get("byte_offset") is not None or cursor is not None:
                raise FileSystemOperationError("invalid_arguments", "start_line cannot be combined with byte offset or cursor")
            offset = self._offset_for_line(path, self._bounded_int(start_line, 1, 10**9, "start_line"))
        else:
            offset = self._bounded_int(byte_offset, 0, max(path.stat().st_size, 0), "byte_offset")
        data, next_offset = self._read_bounded(path, offset, max_bytes, max_lines)
        has_more = next_offset < path.stat().st_size
        next_cursor = self._encode_cursor(self._relative(path, workspace), next_offset) if has_more else None
        return FileSystemActionResponse(
            status="success",
            payload={
                "path": self._relative(path, workspace),
                "content": data.decode("utf-8", errors="replace"),
                "byte_offset": offset,
                "bytes_returned": len(data),
                "has_more": has_more,
            },
            next_cursor=next_cursor,
        )

    def _write_file(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        path = self._path(workspace, self._required_str(args, "path"))
        content = self._required_str(args, "content", allow_empty=True)
        mode = str(args.get("mode", "create"))
        if mode not in {"create", "overwrite", "append"}:
            raise FileSystemOperationError("invalid_arguments", "mode must be create, overwrite, or append")
        data = content.encode("utf-8")
        self._check_write_size(data)
        exists = path.exists() or path.is_symlink()
        if path.is_symlink():
            raise FileSystemOperationError("invalid_path", "Writing through a symlink is not allowed")
        if mode == "create" and exists:
            raise FileSystemOperationError("already_exists", "Path already exists")
        if mode == "append" and exists:
            if not path.is_file():
                raise FileSystemOperationError("not_file", "Path is not a regular file")
            existing = path.read_bytes()
            data = existing + data
        self._check_quota(workspace, path, len(data))
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._validate_existing_components(path.parent, workspace)
        self._atomic_write(path, data)
        return self._success({"path": self._relative(path, workspace), "metadata": self._metadata(path, workspace), "response_truncated": False})

    def _patch_file(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        path = self._path(workspace, self._required_str(args, "path"))
        self._require_regular_text_file(path)
        patch = self._required_str(args, "patch")
        self._check_patch_size(patch)
        original = path.read_text(encoding="utf-8")
        proposed = self._apply_unified_patch(original, patch)
        data = proposed.encode("utf-8")
        self._check_write_size(data)
        self._check_quota(workspace, path, len(data))
        self._atomic_write(path, data)
        return self._success({"path": self._relative(path, workspace), "metadata": self._metadata(path, workspace)})

    def _preview_diff(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        path = self._path(workspace, self._required_str(args, "path"))
        original = ""
        if path.exists():
            self._require_regular_text_file(path)
            original = path.read_text(encoding="utf-8")
        proposed_content = args.get("proposed_content")
        patch = args.get("patch")
        if (proposed_content is None) == (patch is None):
            raise FileSystemOperationError("invalid_arguments", "Provide exactly one of proposed_content or patch")
        if patch is not None:
            patch_text = str(patch)
            self._check_patch_size(patch_text)
            proposed = self._apply_unified_patch(original, patch_text)
        else:
            proposed = str(proposed_content)
            self._check_write_size(proposed.encode("utf-8"))
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile=f"a/{self._relative(path, workspace)}",
                tofile=f"b/{self._relative(path, workspace)}",
            )
        )
        encoded = diff.encode("utf-8")
        truncated = len(encoded) > MAX_DIFF_BYTES
        if truncated:
            diff = encoded[:MAX_DIFF_BYTES].decode("utf-8", errors="replace")
        return self._success({"path": self._relative(path, workspace), "diff": diff, "truncated": truncated})

    def _mkdir(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        path = self._path(workspace, self._required_str(args, "path"))
        parents = self._bool(args, "parents", False)
        try:
            path.mkdir(mode=0o700, parents=parents, exist_ok=False)
        except FileExistsError as exc:
            raise FileSystemOperationError("already_exists", "Path already exists") from exc
        return self._success({"path": self._relative(path, workspace), "metadata": self._metadata(path, workspace)})

    def _copy(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        source = self._path(workspace, self._required_str(args, "source"))
        destination = self._path(workspace, self._required_str(args, "destination"))
        overwrite = self._bool(args, "overwrite", False)
        self._require_existing(source)
        if source.is_symlink():
            raise FileSystemOperationError("invalid_path", "Copying symlinks is not allowed")
        exists = destination.exists() or destination.is_symlink()
        if exists and not overwrite:
            raise FileSystemOperationError("already_exists", "Destination already exists")
        size = self._tree_size(source)
        self._check_quota(workspace, destination, size)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if exists:
            self._remove(destination)
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=False)
        else:
            shutil.copy2(source, destination)
        return self._success({"source": self._relative(source, workspace), "destination": self._relative(destination, workspace), "metadata": self._metadata(destination, workspace)})

    def _move(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        source = self._path(workspace, self._required_str(args, "source"))
        destination = self._path(workspace, self._required_str(args, "destination"))
        overwrite = self._bool(args, "overwrite", False)
        self._require_existing(source)
        if source == destination:
            raise FileSystemOperationError("invalid_arguments", "Source and destination must differ")
        if source.is_dir():
            try:
                destination.relative_to(source)
            except ValueError:
                pass
            else:
                raise FileSystemOperationError("invalid_path", "Cannot move a directory into itself")
        exists = destination.exists() or destination.is_symlink()
        if exists and not overwrite:
            raise FileSystemOperationError("already_exists", "Destination already exists")
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if exists:
            self._remove(destination)
        os.replace(source, destination)
        return self._success({"source": self._relative(source, workspace), "destination": self._relative(destination, workspace), "metadata": self._metadata(destination, workspace)})

    def _delete(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        path = self._path(workspace, self._required_str(args, "path"))
        self._require_existing(path)
        recursive = self._bool(args, "recursive", False)
        if path.is_dir() and not path.is_symlink() and not recursive:
            raise FileSystemOperationError("recursive_required", "Directories require recursive=true")
        self._remove(path)
        return self._success({"path": self._relative(path, workspace), "deleted": True})

    def _batch(self, workspace: Path, args: dict[str, Any]) -> FileSystemActionResponse:
        operations = args.get("operations")
        if not isinstance(operations, list) or not operations:
            raise FileSystemOperationError("invalid_arguments", "operations must be a non-empty array")
        if len(operations) > MAX_BATCH_OPERATIONS:
            raise FileSystemOperationError("limit_exceeded", f"batch supports at most {MAX_BATCH_OPERATIONS} operations")
        continue_on_error = self._bool(args, "continue_on_error", False)
        results: list[dict[str, Any]] = []
        overall = "success"
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict) or not isinstance(operation.get("action"), str) or not isinstance(operation.get("arguments"), dict):
                result = FileSystemActionResponse(status="error", error_code="invalid_arguments", message=f"Invalid operation at index {index}")
            else:
                try:
                    result = self._dispatch(workspace, operation["action"], operation["arguments"], allow_batch=False)
                except FileSystemOperationError as exc:
                    result = FileSystemActionResponse(status="error", payload=exc.payload, error_code=exc.code, message=exc.message)
            results.append({"index": index, "action": operation.get("action") if isinstance(operation, dict) else None, "result": result.model_dump(mode="json")})
            if result.status != "success":
                overall = result.status
                if not continue_on_error:
                    break
        return FileSystemActionResponse(status=overall, payload={"results": results, "completed": len(results), "total": len(operations)})

    def _path(self, workspace: Path, raw: Any, *, allow_root: bool = False) -> Path:
        if not isinstance(raw, str):
            raise FileSystemOperationError("invalid_path", "Path must be a string")
        if "\x00" in raw or any(ord(char) < 32 for char in raw):
            raise FileSystemOperationError("invalid_path", "Path contains control characters")
        if unicodedata.normalize("NFC", raw) != raw:
            raise FileSystemOperationError("invalid_path", "Path must use canonical Unicode NFC normalization")
        decoded = raw
        for _ in range(3):
            next_decoded = unquote(decoded)
            if next_decoded == decoded:
                break
            decoded = next_decoded
        decoded_parts = decoded.replace("\\", "/").split("/")
        if decoded != raw and (".." in decoded_parts or "/" in decoded or "\\" in decoded):
            raise FileSystemOperationError("invalid_path", "URL-encoded traversal or separators are not allowed")
        candidate = Path(raw)
        if candidate.is_absolute() or "\\" in raw:
            raise FileSystemOperationError("invalid_path", "Only workspace-relative POSIX paths are allowed")
        parts = [part for part in candidate.parts if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise FileSystemOperationError("sandbox_violation", "Path traversal outside the workspace is blocked")
        if parts and parts[0] in RESERVED_NAMES:
            raise FileSystemOperationError("invalid_path", "Path uses a reserved workspace name")
        if not parts and not allow_root:
            raise FileSystemOperationError("invalid_path", "The workspace root is not a valid target")
        path = workspace.joinpath(*parts)
        self._require_under(path.absolute(), workspace)
        self._validate_existing_components(path, workspace)
        return path

    def _validate_existing_components(self, path: Path, workspace: Path) -> None:
        current = workspace
        try:
            relative_parts = path.absolute().relative_to(workspace).parts
        except ValueError as exc:
            raise FileSystemOperationError("sandbox_violation", "Path escaped the workspace") from exc
        for part in relative_parts:
            current = current / part
            if current.exists() or current.is_symlink():
                resolved = current.resolve()
                try:
                    resolved.relative_to(workspace.resolve())
                except ValueError as exc:
                    raise FileSystemOperationError("sandbox_violation", "Symlink escape outside the workspace is blocked") from exc

    def _require_under(self, path: Path, parent: Path) -> None:
        try:
            path.relative_to(parent)
        except ValueError as exc:
            raise FileSystemOperationError("sandbox_violation", "Path escaped the workspace root") from exc

    def _metadata(self, path: Path, workspace: Path) -> dict[str, Any]:
        details = path.lstat()
        if stat_module.S_ISLNK(details.st_mode):
            kind = "symlink"
        elif stat_module.S_ISDIR(details.st_mode):
            kind = "directory"
        elif stat_module.S_ISREG(details.st_mode):
            kind = "file"
        else:
            kind = "other"
        return {
            "name": path.name or ".",
            "path": self._relative(path, workspace),
            "type": kind,
            "size": details.st_size,
            "modified_at": self._timestamp(details.st_mtime),
            "created_at": self._timestamp(details.st_ctime),
            "permissions": stat_module.filemode(details.st_mode),
            "readable": os.access(path, os.R_OK),
            "writable": os.access(path, os.W_OK),
        }

    def _relative(self, path: Path, workspace: Path) -> str:
        value = path.absolute().relative_to(workspace).as_posix()
        return value or "."

    def _timestamp(self, seconds: float) -> str:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()

    def _is_binary(self, path: Path) -> bool:
        with path.open("rb") as handle:
            sample = handle.read(8192)
        if b"\x00" in sample:
            return True
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return True
        return False

    def _require_regular_text_file(self, path: Path) -> None:
        self._require_existing(path)
        if path.is_symlink() or not path.is_file():
            raise FileSystemOperationError("not_file", "Path is not a regular file")
        if self._is_binary(path):
            raise FileSystemOperationError("binary_file", "Binary file content is not returned")

    def _require_existing(self, path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            raise FileSystemOperationError("not_found", "Path does not exist")

    def _find_text(self, path: Path, query: str, snippet_chars: int) -> dict[str, Any] | None:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            consumed = 0
            for line_number, line in enumerate(handle, start=1):
                consumed += len(line.encode("utf-8"))
                if consumed > 2 * 1024 * 1024:
                    return None
                index = line.find(query)
                if index >= 0:
                    before = max(0, index - snippet_chars // 2)
                    return {"line": line_number, "snippet": line[before : before + snippet_chars].strip()}
        return None

    def _matches_glob(self, relative_path: str, pattern: str) -> bool:
        patterns = [pattern]
        if pattern.startswith("**/"):
            patterns.append(pattern[3:])
        return any(
            fnmatch.fnmatch(relative_path, candidate) or Path(relative_path).match(candidate)
            for candidate in patterns
        )

    def _offset_for_line(self, path: Path, start_line: int) -> int:
        if start_line == 1:
            return 0
        offset = 0
        with path.open("rb") as handle:
            for _ in range(start_line - 1):
                line = handle.readline()
                if not line:
                    return offset
                offset += len(line)
        return offset

    def _read_bounded(self, path: Path, offset: int, max_bytes: int, max_lines: int) -> tuple[bytes, int]:
        chunks: list[bytes] = []
        total = 0
        with path.open("rb") as handle:
            handle.seek(offset)
            for _ in range(max_lines):
                remaining = max_bytes - total
                if remaining <= 0:
                    break
                line = handle.readline(remaining)
                if not line:
                    break
                chunks.append(line)
                total += len(line)
                if len(line) == remaining:
                    break
            return b"".join(chunks), handle.tell()

    def _encode_cursor(self, path: str, offset: int) -> str:
        raw = json.dumps({"p": path, "o": offset}, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _decode_cursor(self, cursor: str, expected_path: str) -> int:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            value = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            if value.get("p") != expected_path or not isinstance(value.get("o"), int) or value["o"] < 0:
                raise ValueError
            return value["o"]
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
            raise FileSystemOperationError("invalid_cursor", "Cursor is invalid for this file") from exc

    def _atomic_write(self, path: Path, data: bytes) -> None:
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _apply_unified_patch(self, original: str, patch: str) -> str:
        source = original.splitlines(keepends=True)
        patch_lines = patch.splitlines(keepends=True)
        output: list[str] = []
        source_index = 0
        index = 0
        saw_hunk = False
        while index < len(patch_lines):
            line = patch_lines[index]
            match = HUNK_RE.match(line)
            if not match:
                index += 1
                continue
            saw_hunk = True
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            consumed_old = 0
            produced_new = 0
            target_index = max(old_start - 1, 0)
            if target_index < source_index:
                raise FileSystemOperationError("patch_conflict", "Patch hunks overlap or are out of order")
            output.extend(source[source_index:target_index])
            source_index = target_index
            index += 1
            while index < len(patch_lines) and not patch_lines[index].startswith("@@"):
                patch_line = patch_lines[index]
                if patch_line.startswith(("--- ", "+++ ")):
                    index += 1
                    continue
                if patch_line.startswith("\\ No newline"):
                    index += 1
                    continue
                prefix = patch_line[:1]
                content = patch_line[1:]
                if prefix == " ":
                    if source_index >= len(source) or source[source_index] != content:
                        self._patch_conflict(source, source_index, content)
                    output.append(source[source_index])
                    source_index += 1
                    consumed_old += 1
                    produced_new += 1
                elif prefix == "-":
                    if source_index >= len(source) or source[source_index] != content:
                        self._patch_conflict(source, source_index, content)
                    source_index += 1
                    consumed_old += 1
                elif prefix == "+":
                    output.append(content)
                    produced_new += 1
                else:
                    raise FileSystemOperationError("invalid_patch", "Malformed unified diff line")
                index += 1
            if consumed_old != old_count or produced_new != new_count:
                raise FileSystemOperationError(
                    "invalid_patch",
                    "Unified diff hunk line counts do not match its header",
                )
        if not saw_hunk:
            raise FileSystemOperationError("invalid_patch", "Patch contains no unified diff hunks")
        output.extend(source[source_index:])
        return "".join(output)

    def _patch_conflict(self, source: list[str], index: int, expected: str) -> None:
        actual = "" if index >= len(source) else source[index]
        raise FileSystemOperationError(
            "patch_conflict",
            "Patch does not apply to the current file content",
            {"line": index + 1, "expected": expected[:240], "actual": actual[:240]},
        )

    def _check_patch_size(self, patch: str) -> None:
        if len(patch.encode("utf-8")) > MAX_PATCH_BYTES:
            raise FileSystemOperationError("write_limit_exceeded", "Patch exceeds the maximum size")

    def _check_write_size(self, data: bytes) -> None:
        if len(data) > self._max_write_bytes:
            raise FileSystemOperationError("write_limit_exceeded", "Content exceeds the maximum write size")

    def _check_quota(self, workspace: Path, target: Path, new_size: int) -> None:
        current = self._tree_size(workspace, exclude_reserved=True)
        replaced = self._tree_size(target) if target.exists() and not target.is_symlink() else 0
        if current - replaced + new_size > self._workspace_quota_bytes:
            raise FileSystemOperationError("workspace_quota_exceeded", "Operation would exceed the workspace quota")

    def _tree_size(self, path: Path, *, exclude_reserved: bool = False) -> int:
        if not path.exists() or path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_size
        total = 0
        for root, directories, files in os.walk(path, followlinks=False):
            if exclude_reserved and Path(root) == path:
                directories[:] = [name for name in directories if name not in RESERVED_NAMES]
            for name in files:
                candidate = Path(root) / name
                if not candidate.is_symlink():
                    total += candidate.stat().st_size
        return total

    def _remove(self, path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()

    def _required_str(self, args: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
        value = args.get(key)
        if not isinstance(value, str) or (not allow_empty and not value):
            raise FileSystemOperationError("invalid_arguments", f"{key} must be a{' non-empty' if not allow_empty else ''} string")
        return value

    def _bool(self, args: dict[str, Any], key: str, default: bool) -> bool:
        value = args.get(key, default)
        if not isinstance(value, bool):
            raise FileSystemOperationError("invalid_arguments", f"{key} must be a boolean")
        return value

    def _bounded_int(self, value: Any, minimum: int, maximum: int, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise FileSystemOperationError("invalid_arguments", f"{name} must be an integer")
        return max(minimum, min(value, maximum))

    def _success(self, payload: dict[str, Any]) -> FileSystemActionResponse:
        return FileSystemActionResponse(status="success", payload=payload)

def get_file_system_service() -> FileSystemService:
    return FileSystemService(
        workspace_root=DEFAULT_WORKSPACE_ROOT,
        max_read_bytes=int(os.getenv("FILE_SYSTEM_MAX_READ_BYTES", str(DEFAULT_MAX_READ_BYTES))),
        max_write_bytes=int(os.getenv("FILE_SYSTEM_MAX_WRITE_BYTES", str(DEFAULT_MAX_WRITE_BYTES))),
        workspace_quota_bytes=int(
            os.getenv("FILE_SYSTEM_WORKSPACE_QUOTA_BYTES", str(DEFAULT_WORKSPACE_QUOTA_BYTES))
        ),
    )
