"""A tiny stdio MCP server for tests. Speaks newline-delimited JSON-RPC on stdin/stdout."""

import json
import os
import stat
import sys
import threading
import time

print("fake-mcp starting (banner, not JSON)", flush=True)
print("fake-mcp stderr log line", file=sys.stderr, flush=True)

if os.environ.get("FAKE_EXIT_AT_START"):
    print("fatal: refusing to start", file=sys.stderr, flush=True)
    sys.exit(3)

write_lock = threading.Lock()
client_responses: dict[str, dict] = {}
client_response_ready = threading.Event()


def send(message: dict) -> None:
    with write_lock:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()


def result(request_id, value) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "result": value})


def text(request_id, value: str) -> None:
    result(request_id, {"content": [{"type": "text", "text": value}]})


def call_tool(request_id, name: str, arguments: dict) -> None:
    if name == "echo":
        time.sleep(float(arguments.get("delay", 0)))
        text(request_id, arguments.get("text", ""))
    elif name == "env":
        text(request_id, json.dumps(dict(os.environ)))
    elif name == "read_file":
        path = os.environ[arguments["env"]]
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        text(request_id, json.dumps({"content": content, "mode": oct(stat.S_IMODE(os.stat(path).st_mode))}))
    elif name == "ask_client":
        send({"jsonrpc": "2.0", "id": "server-1", "method": "roots/list"})
        client_response_ready.wait(5)
        text(request_id, json.dumps(client_responses.get("server-1")))
    elif name == "crash":
        print("crashing on purpose", file=sys.stderr, flush=True)
        os._exit(7)
    elif name == "big":
        text(request_id, "x" * int(arguments["size"]))
    elif name == "hang":
        time.sleep(60)
    else:
        send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": f"unknown tool {name}"}})


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method is None:
        client_responses[str(message.get("id"))] = message
        client_response_ready.set()
        continue
    if "id" not in message:
        continue
    if method == "initialize":
        result(
            message["id"],
            {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp", "version": "1.2.3"},
            },
        )
    elif method == "tools/list":
        result(message["id"], {"tools": [{"name": "echo"}, {"name": "env"}]})
    elif method == "tools/call":
        params = message["params"]
        threading.Thread(target=call_tool, args=(message["id"], params["name"], params.get("arguments", {}))).start()
