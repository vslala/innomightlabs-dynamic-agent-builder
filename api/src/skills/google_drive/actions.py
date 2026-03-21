from __future__ import annotations

from io import BytesIO
from typing import Any

import httpx

from src.auth.google_drive_oauth import ensure_valid_google_drive_credentials
from src.settings.repository import ProviderSettingsRepository

from collections import deque

GOOGLE_DRIVE_FILES_API = "https://www.googleapis.com/drive/v3/files"
GOOGLE_DRIVE_EXPORT_API = "https://www.googleapis.com/drive/v3/files/{file_id}/export"
GOOGLE_DRIVE_DOWNLOAD_API = "https://www.googleapis.com/drive/v3/files/{file_id}"
FILE_FIELDS = "id,name,mimeType,modifiedTime,size,trashed,webViewLink,parents,driveId,shortcutDetails(targetId,targetMimeType)"
MAX_READ_CHARACTERS = 20000
TEXT_LIKE_MIME_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-javascript",
)
TEXT_LIKE_EXACT_MIME_TYPES = {
    "application/rtf",
    "application/x-sh",
    "application/sql",
}
GOOGLE_DOC_MIME_TYPE = "application/vnd.google-apps.document"
PDF_MIME_TYPE = "application/pdf"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
ALLOWED_ORDER_BY = {
    "modifiedTime desc",
    "modifiedTime asc",
    "name",
    "name desc",
    "createdTime desc",
    "createdTime asc",
}
COMMON_LIST_PARAMS = {
    "supportsAllDrives": "true",
    "includeItemsFromAllDrives": "true",
}
COMMON_FILE_PARAMS = {
    "supportsAllDrives": "true",
}


def _require_owner_email(context: dict[str, Any]) -> str:
    owner_email = str(context.get("owner_email", "")).strip()
    if not owner_email:
        raise ValueError("Missing skill runtime owner context")
    return owner_email


async def _get_access_token(context: dict[str, Any]) -> str:
    owner_email = _require_owner_email(context)
    repo = ProviderSettingsRepository()
    provider_settings = repo.find_by_provider(owner_email, "GoogleDrive")
    if not provider_settings:
        raise ValueError("Google Drive account is not connected for the agent owner")

    credentials = await ensure_valid_google_drive_credentials(provider_settings, repo)
    return credentials.access_token


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def _clamp_page_size(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 10
    return max(1, min(20, parsed))


def _escape_drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _is_text_like_mime_type(mime_type: str) -> bool:
    if mime_type in TEXT_LIKE_EXACT_MIME_TYPES:
        return True
    return any(mime_type.startswith(prefix) for prefix in TEXT_LIKE_MIME_PREFIXES)


def _truncate_text(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_READ_CHARACTERS:
        return text, False
    return text[:MAX_READ_CHARACTERS], True


def _format_file_summary(item: dict[str, Any]) -> str:
    kind = "folder" if item.get("mimeType") == FOLDER_MIME_TYPE else "file"
    shortcut_details = item.get("shortcutDetails") or {}
    shortcut_target_id = shortcut_details.get("targetId")
    drive_id = item.get("driveId", "")
    parents = item.get("parents") or []
    extra_parts: list[str] = []
    if shortcut_target_id:
        extra_parts.append(f"shortcut_target_id={shortcut_target_id}")
    if drive_id:
        extra_parts.append(f"drive_id={drive_id}")
    if parents:
        extra_parts.append(f"parents={parents}")
    extra = f" | {' | '.join(extra_parts)}" if extra_parts else ""
    return (
        f"- [{item.get('id', '')}] {item.get('name', '(unnamed)')} | type={kind} | "
        f"mime_type={item.get('mimeType', '')} | modified_time={item.get('modifiedTime', '')} | "
        f"size={item.get('size', '')} | trashed={item.get('trashed', False)} | "
        f"web_view_link={item.get('webViewLink', '')}{extra}"
    )


async def _fetch_file_metadata(client: httpx.AsyncClient, file_id: str, access_token: str) -> dict[str, Any]:
    response = await client.get(
        f"{GOOGLE_DRIVE_FILES_API}/{file_id}",
        params={"fields": FILE_FIELDS, **COMMON_FILE_PARAMS},
        headers=_headers(access_token),
    )
    if not response.is_success:
        raise RuntimeError(f"Google Drive metadata request failed ({response.status_code}): {response.text[:400]}")
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def _fetch_file_metadata_optional(client: httpx.AsyncClient, file_id: str, access_token: str) -> dict[str, Any] | None:
    try:
        return await _fetch_file_metadata(client, file_id, access_token)
    except Exception:
        return None


async def _list_files(
    client: httpx.AsyncClient,
    *,
    access_token: str,
    query_string: str,
    page_size: int,
    order_by: str,
    drive_id: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "q": query_string,
        "pageSize": page_size,
        "fields": f"files({FILE_FIELDS})",
        "orderBy": order_by,
        **COMMON_LIST_PARAMS,
    }
    if drive_id:
        params["corpora"] = "drive"
        params["driveId"] = drive_id
    else:
        params["corpora"] = "allDrives"

    response = await client.get(
        GOOGLE_DRIVE_FILES_API,
        params=params,
        headers=_headers(access_token),
    )
    if not response.is_success:
        raise RuntimeError(f"Google Drive search failed ({response.status_code}): {response.text[:400]}")

    payload = response.json()
    files = payload.get("files") if isinstance(payload, dict) else None
    return [item for item in files if isinstance(item, dict)] if isinstance(files, list) else []


def _normalize_query_terms(
    *,
    mode: str,
    query: str,
    entry_type: str,
    parent_folder_id: str,
    exact_name: bool,
    mime_type: str,
    include_trashed: bool,
) -> list[str]:
    search_terms: list[str] = []
    if mode == "children":
        escaped_parent = _escape_drive_query_value(parent_folder_id)
        search_terms.append(f"'{escaped_parent}' in parents")
    elif parent_folder_id:
        escaped_parent = _escape_drive_query_value(parent_folder_id)
        search_terms.append(f"'{escaped_parent}' in parents")

    if query:
        escaped_query = _escape_drive_query_value(query)
        if exact_name:
            search_terms.append(f"name = '{escaped_query}'")
        elif mode in {"list", "children"}:
            search_terms.append(f"name contains '{escaped_query}'")
        else:
            search_terms.append(
                f"(name contains '{escaped_query}' or fullText contains '{escaped_query}')"
            )

    if entry_type == "folders":
        search_terms.append(f"mimeType = '{FOLDER_MIME_TYPE}'")
    elif entry_type == "files":
        search_terms.append(f"mimeType != '{FOLDER_MIME_TYPE}'")
    if mime_type:
        search_terms.append(f"mimeType = '{_escape_drive_query_value(mime_type)}'")
    if not include_trashed:
        search_terms.append("trashed = false")
    return search_terms


async def _resolve_parent_context(
    client: httpx.AsyncClient,
    *,
    access_token: str,
    parent_folder_id: str,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "requested_parent_id": parent_folder_id,
        "resolved_parent_id": parent_folder_id,
        "requested_parent_found": False,
        "requested_parent_mime_type": "",
        "drive_id": "",
        "shortcut_target_id": "",
        "shortcut_target_found": False,
    }
    parent_metadata = await _fetch_file_metadata_optional(client, parent_folder_id, access_token)
    if not parent_metadata:
        return context

    context["requested_parent_found"] = True
    context["requested_parent_mime_type"] = str(parent_metadata.get("mimeType", "")).strip()
    context["drive_id"] = str(parent_metadata.get("driveId", "")).strip()

    if parent_metadata.get("mimeType") == SHORTCUT_MIME_TYPE:
        shortcut_details = parent_metadata.get("shortcutDetails") or {}
        target_id = str(shortcut_details.get("targetId", "")).strip()
        target_mime_type = str(shortcut_details.get("targetMimeType", "")).strip()
        context["shortcut_target_id"] = target_id
        if target_id and target_mime_type == FOLDER_MIME_TYPE:
            target_metadata = await _fetch_file_metadata_optional(client, target_id, access_token)
            if target_metadata:
                context["shortcut_target_found"] = True
                context["resolved_parent_id"] = target_id
                context["drive_id"] = str(target_metadata.get("driveId", "")).strip() or context["drive_id"]
    return context


async def _list_recursive_children(
    client: httpx.AsyncClient,
    *,
    access_token: str,
    root_folder_id: str,
    page_size: int,
    order_by: str,
    query: str,
    entry_type: str,
    exact_name: bool,
    mime_type: str,
    include_trashed: bool,
    drive_id: str | None,
) -> tuple[list[dict[str, Any]], int]:
    queue: deque[tuple[str, int]] = deque([(root_folder_id, 0)])
    visited_folders: set[str] = set()
    collected: list[dict[str, Any]] = []
    max_depth = 0

    while queue and len(collected) < page_size:
        folder_id, depth = queue.popleft()
        if folder_id in visited_folders:
            continue
        visited_folders.add(folder_id)
        max_depth = max(max_depth, depth)

        child_terms = _normalize_query_terms(
            mode="children",
            query=query,
            entry_type="any",
            parent_folder_id=folder_id,
            exact_name=exact_name,
            mime_type="",
            include_trashed=include_trashed,
        )
        children = await _list_files(
            client,
            access_token=access_token,
            query_string=" and ".join(child_terms),
            page_size=100,
            order_by=order_by,
            drive_id=drive_id,
        )

        for child in children:
            child_with_depth = dict(child)
            child_with_depth["_depth"] = depth + 1
            child_mime = str(child.get("mimeType", "")).strip()
            include_child = True
            if entry_type == "folders" and child_mime != FOLDER_MIME_TYPE:
                include_child = False
            if entry_type == "files" and child_mime == FOLDER_MIME_TYPE:
                include_child = False
            if mime_type and child_mime != mime_type:
                include_child = False

            if include_child:
                collected.append(child_with_depth)
                if len(collected) >= page_size:
                    break

            if child_mime == FOLDER_MIME_TYPE:
                child_id = str(child.get("id", "")).strip()
                if child_id:
                    queue.append((child_id, depth + 1))

    return collected, max_depth


def _build_diagnostics_lines(
    *,
    requested_parent_id: str,
    resolved_parent_context: dict[str, Any] | None,
    recursive: bool,
    diagnostic_mode: bool,
    result_count: int,
    max_depth: int,
) -> list[str]:
    if not diagnostic_mode and not recursive:
        return []

    context = resolved_parent_context or {}
    return [
        "<diagnostics>",
        f"requested_parent_id={requested_parent_id}",
        f"requested_parent_found={context.get('requested_parent_found', False)}",
        f"requested_parent_mime_type={context.get('requested_parent_mime_type', '')}",
        f"resolved_parent_id={context.get('resolved_parent_id', requested_parent_id)}",
        f"shortcut_target_id={context.get('shortcut_target_id', '')}",
        f"shortcut_target_found={context.get('shortcut_target_found', False)}",
        f"drive_id={context.get('drive_id', '')}",
        f"recursive={recursive}",
        f"result_count={result_count}",
        f"max_depth={max_depth}",
        "</diagnostics>",
    ]


async def search(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    del config
    query = str(arguments.get("query", "")).strip()
    mode = str(arguments.get("mode", "search")).strip().lower() or "search"
    entry_type = str(arguments.get("entry_type", "any")).strip().lower() or "any"
    parent_folder_id = str(arguments.get("parent_folder_id", "")).strip()
    exact_name = bool(arguments.get("exact_name", False))
    recursive = bool(arguments.get("recursive", False))
    diagnostics = bool(arguments.get("diagnostics", False))
    if not query:
        if mode == "search" and not parent_folder_id:
            raise ValueError("Missing required argument: query")
        if exact_name:
            raise ValueError("exact_name requires a query value")

    if mode not in {"search", "list", "children"}:
        raise ValueError("Invalid mode. Allowed values: search, list, children")
    if entry_type not in {"any", "files", "folders"}:
        raise ValueError("Invalid entry_type. Allowed values: any, files, folders")
    if mode == "children" and not parent_folder_id:
        raise ValueError("parent_folder_id is required when mode=children")

    page_size = _clamp_page_size(arguments.get("page_size", 10))
    mime_type = str(arguments.get("mime_type", "")).strip()
    include_trashed = bool(arguments.get("include_trashed", False))
    order_by = str(arguments.get("order_by", "modifiedTime desc")).strip() or "modifiedTime desc"
    if order_by not in ALLOWED_ORDER_BY:
        order_by = "modifiedTime desc"
    access_token = await _get_access_token(context)

    search_terms = _normalize_query_terms(
        mode=mode,
        query=query,
        entry_type=entry_type,
        parent_folder_id=parent_folder_id,
        exact_name=exact_name,
        mime_type=mime_type,
        include_trashed=include_trashed,
    )

    query_string = " and ".join(search_terms)
    resolved_parent_context: dict[str, Any] | None = None
    max_depth = 0

    async with httpx.AsyncClient(timeout=20.0) as client:
        if mode == "children" and recursive:
            resolved_parent_context = await _resolve_parent_context(
                client,
                access_token=access_token,
                parent_folder_id=parent_folder_id,
            )
            resolved_parent_id = str(
                (resolved_parent_context or {}).get("resolved_parent_id", parent_folder_id)
            ).strip() or parent_folder_id
            resolved_drive_id = str((resolved_parent_context or {}).get("drive_id", "")).strip() or None
            files, max_depth = await _list_recursive_children(
                client,
                access_token=access_token,
                root_folder_id=resolved_parent_id,
                page_size=page_size,
                order_by=order_by,
                query=query,
                entry_type=entry_type,
                exact_name=exact_name,
                mime_type=mime_type,
                include_trashed=include_trashed,
                drive_id=resolved_drive_id,
            )
        else:
            files = await _list_files(
                client,
                access_token=access_token,
                query_string=query_string,
                page_size=page_size,
                order_by=order_by,
            )

            if not files and mode == "children" and parent_folder_id:
                resolved_parent_context = await _resolve_parent_context(
                    client,
                    access_token=access_token,
                    parent_folder_id=parent_folder_id,
                )
                if resolved_parent_context.get("requested_parent_found"):
                    retry_parent_id = str(resolved_parent_context.get("resolved_parent_id", parent_folder_id)).strip()
                    retry_drive_id = str(resolved_parent_context.get("drive_id", "")).strip() or None
                    retry_terms = [term for term in search_terms if not term.endswith(" in parents")]
                    retry_terms.insert(0, f"'{_escape_drive_query_value(retry_parent_id)}' in parents")
                    files = await _list_files(
                        client,
                        access_token=access_token,
                        query_string=" and ".join(retry_terms),
                        page_size=page_size,
                        order_by=order_by,
                        drive_id=retry_drive_id,
                    )

    if not files:
        diagnostic_lines = _build_diagnostics_lines(
            requested_parent_id=parent_folder_id,
            resolved_parent_context=resolved_parent_context,
            recursive=recursive,
            diagnostic_mode=diagnostics,
            result_count=0,
            max_depth=max_depth,
        )
        if diagnostic_lines:
            return "\n".join(["No Google Drive files found for those filters.", *diagnostic_lines])
        return "No Google Drive files found for those filters."

    heading = "Google Drive results:"
    if mode == "children":
        heading = f"Google Drive children for folder {parent_folder_id}:"
        if recursive:
            heading = f"Google Drive recursive children for folder {parent_folder_id}:"
    elif mode == "list":
        heading = "Google Drive listing:"

    lines = [heading]
    lines.extend(
        _build_diagnostics_lines(
            requested_parent_id=parent_folder_id,
            resolved_parent_context=resolved_parent_context,
            recursive=recursive,
            diagnostic_mode=diagnostics,
            result_count=len(files),
            max_depth=max_depth,
        )
    )
    for item in files:
        if isinstance(item, dict):
            lines.append(_format_file_summary(item))
    return "\n".join(lines)


async def read(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    del config
    file_id = str(arguments.get("file_id", "")).strip()
    if not file_id:
        raise ValueError("Missing required argument: file_id")

    access_token = await _get_access_token(context)

    async with httpx.AsyncClient(timeout=30.0) as client:
        metadata = await _fetch_file_metadata(client, file_id, access_token)
        mime_type = str(metadata.get("mimeType", "")).strip()

        if mime_type == GOOGLE_DOC_MIME_TYPE:
            response = await client.get(
                GOOGLE_DRIVE_EXPORT_API.format(file_id=file_id),
                params={"mimeType": "text/plain", **COMMON_FILE_PARAMS},
                headers=_headers(access_token),
            )
            if not response.is_success:
                raise RuntimeError(f"Google Drive export failed ({response.status_code}): {response.text[:400]}")
            text = response.text
        elif mime_type == PDF_MIME_TYPE:
            from pypdf import PdfReader

            response = await client.get(
                GOOGLE_DRIVE_DOWNLOAD_API.format(file_id=file_id),
                params={"alt": "media", **COMMON_FILE_PARAMS},
                headers=_headers(access_token),
            )
            if not response.is_success:
                raise RuntimeError(f"Google Drive download failed ({response.status_code}): {response.text[:400]}")
            reader = PdfReader(BytesIO(response.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        elif _is_text_like_mime_type(mime_type):
            response = await client.get(
                GOOGLE_DRIVE_DOWNLOAD_API.format(file_id=file_id),
                params={"alt": "media", **COMMON_FILE_PARAMS},
                headers=_headers(access_token),
            )
            if not response.is_success:
                raise RuntimeError(f"Google Drive download failed ({response.status_code}): {response.text[:400]}")
            text = response.content.decode("utf-8", errors="replace")
        else:
            raise ValueError(
                f"Unsupported Google Drive file type for read: {mime_type or 'unknown'}"
            )

    text = text.strip()
    truncated_text, was_truncated = _truncate_text(text)

    lines = [
        "Google Drive file:",
        _format_file_summary(metadata),
        f"content_truncated={was_truncated}",
        "content:",
        truncated_text or "(empty file)",
    ]
    return "\n".join(lines)


async def delete(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    del config
    file_id = str(arguments.get("file_id", "")).strip()
    if not file_id:
        raise ValueError("Missing required argument: file_id")

    access_token = await _get_access_token(context)

    async with httpx.AsyncClient(timeout=20.0) as client:
        metadata = await _fetch_file_metadata(client, file_id, access_token)
        response = await client.patch(
            f"{GOOGLE_DRIVE_FILES_API}/{file_id}",
            params={"fields": FILE_FIELDS, **COMMON_FILE_PARAMS},
            headers={**_headers(access_token), "Content-Type": "application/json"},
            json={"trashed": True},
        )

    if not response.is_success:
        raise RuntimeError(f"Google Drive trash request failed ({response.status_code}): {response.text[:400]}")

    payload = response.json()
    name = payload.get("name") if isinstance(payload, dict) else metadata.get("name", "")
    return f"Moved Google Drive file to trash: [{file_id}] {name or '(unnamed)'}"
