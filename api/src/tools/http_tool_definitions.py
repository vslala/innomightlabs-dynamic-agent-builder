"""HTTP native tool definitions.

These are intentionally simple and verb-specific so the LLM can use them intuitively.
"""

HTTP_GET = {
    "name": "http_get",
    "description": (
        "Make an HTTP GET request to a public URL. Supports optional headers and query params. "
        "Do NOT include secrets unless absolutely necessary."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL (http/https)"},
            "headers": {"type": "object", "description": "Optional headers as key/value"},
            "query": {"type": "object", "description": "Optional query parameters as key/value"},
        },
        "required": ["url"],
    },
}

HTTP_DELETE = {
    "name": "http_delete",
    "description": "Make an HTTP DELETE request. Supports optional headers and query params.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "query": {"type": "object"},
        },
        "required": ["url"],
    },
}

HTTP_POST = {
    "name": "http_post",
    "description": (
        "Make an HTTP POST request. Use json_body for JSON APIs or text_body for raw text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "query": {"type": "object"},
            "json_body": {"type": "object", "description": "JSON body (object/array)"},
            "text_body": {"type": "string", "description": "Raw body (string)"},
        },
        "required": ["url"],
    },
}

HTTP_PUT = {
    "name": "http_put",
    "description": "Make an HTTP PUT request. Use json_body or text_body.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "query": {"type": "object"},
            "json_body": {"type": "object"},
            "text_body": {"type": "string"},
        },
        "required": ["url"],
    },
}

HTTP_PATCH = {
    "name": "http_patch",
    "description": "Make an HTTP PATCH request. Use json_body or text_body.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "query": {"type": "object"},
            "json_body": {"type": "object"},
            "text_body": {"type": "string"},
        },
        "required": ["url"],
    },
}

HTTP_TOOLS = [HTTP_GET, HTTP_POST, HTTP_PUT, HTTP_PATCH, HTTP_DELETE]
