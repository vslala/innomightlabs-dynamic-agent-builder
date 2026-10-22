# Infra CLI Runner

Private Railway sidecar for running approved infrastructure CLIs behind the API skill runtime.

The service intentionally exposes only:

- `GET /health`
- `POST /v1/commands`
- `POST /v1/python/executions`
- `POST /v1/filesystem/actions`
- `POST /v1/browser/render`
- `POST /v1/browser/inspections`
- `POST /v1/browser/walkthroughs`
- `POST /v1/browser/scenes`
- `POST /v1/media/compositions`, `POST /v1/media/probes`
- `GET /v1/mcp/packages`, `PUT|GET|DELETE /v1/mcp/servers/{server_id}`, `POST /v1/mcp/servers/{server_id}/mcp`

Requests must use bearer auth with `CLI_RUNNER_SHARED_TOKEN`. The runner never accepts shell command strings.

## Browser rendering

`POST /v1/browser/render` with `{url, timeout_seconds, user_agent}` returns `{final_url, status, html}`: the page's HTML
after its scripts have run, for sites that paint their content in the browser (React, Angular). The crawler calls it only
when a plain fetch finds no text. It is a typed operation: no scripts, selectors or cookies go in.

Chromium never opens a socket itself. Every request the page makes is intercepted and sent through `outbound.py`, which
connects only to public addresses, and the response is handed back to the page. A redirect goes back as a redirect, so
each hop is checked; images, fonts, media, web sockets and service workers are refused. A URL that points at localhost or
Railway's private network fails with `502`. `outbound.py` is a copy of the async half of `api/src/common/outbound.py`.

Pages render one at a time (`BROWSER_RENDER_CONCURRENCY`, default `1`) and time out after `timeout_seconds`, capped by
`BROWSER_RENDER_MAX_TIMEOUT_SECONDS` (default `60`). A page that never goes idle returns what it had painted. Chromium
runs with `--no-sandbox`, which a container without user namespaces needs; the network guard above is what keeps a page
away from the private network. Locally, install the browser once with `uv run playwright install chromium`; the render
tests skip themselves without it.

## Page inspection

`POST /v1/browser/inspections` with `{request_id, workspace_id, url, viewport, scroll_through, roles, query, max_elements,
screenshot_path, annotate, include_outline, max_heading_level, timeout_seconds}` tells an agent what is on a page so the steps it writes use targets that
exist. It returns the `elements` a person could act on, the `sections` (headings down to `max_heading_level`, default 2, with
their position down the page), and a `screenshot` saved in the conversation workspace. The accessibility `outline` (cut to
12 KB) is about half the size of a response and the sections already give the page's shape, so it only comes with
`include_outline: true`. Responses leave out nulls, names a target already repeats, and boxes, to spend an agent's tokens
on the page and not on the format.

Each element carries a `target` (`{role, name}`, or a test id, id, exact text or CSS path, with `nth` when several match; a name over 80 characters gets a selector instead)
that the runner has already checked resolves to exactly that element; an element it can't single out is left out. Boxes
are fractions of the whole page. The page is scrolled through first (`scroll_through`) so content that loads on scroll is
present, then read from the top. Content that loads on scroll isn't on the page until it has been scrolled to, so a later
walkthrough must scroll before it targets such an element.

Unlike `/v1/browser/render`, images, fonts and media are fetched (the screenshot should look like the page), through the
same network guard. Inspections use their own slot (`BROWSER_STUDIO_CONCURRENCY`, default `1`) and time out after
`timeout_seconds`, capped by `BROWSER_STUDIO_MAX_INSPECT_SECONDS` (default `60`). `screenshot_path` is a workspace-relative
`.png` and follows the File System skill's path and quota rules; it defaults to `inspect/<id>.png`.

`steps` (up to 30, the same typed steps as a walkthrough) bring the page to a state before it is read, such as an open
menu. They run like a rehearsal. A step that fails stops the rest, and the page as far as it got is still described, with
each step's outcome in `steps`.

## Walkthroughs

`POST /v1/browser/walkthroughs` performs a list of typed steps in the browser, in order, and unless it is a rehearsal
records the screen as a `.webm` in the conversation workspace. Request: `{request_id, workspace_id, url, steps, output_path,
viewport, show_cursor, rehearse, max_duration_seconds, step_timeout_seconds}`.

Steps are data, never code; each kind is one strategy class in `studio/steps.py`:

| `action` | Fields | Notes |
| --- | --- | --- |
| `goto` | `url` | http or https only |
| `click`, `hover` | `target`, `move_ms` | scrolls the target into view; when recording, the cursor glides to it |
| `type` | `target`, `text`, `delay_ms` | clicks to focus, then types key by key |
| `press` | `key` | e.g. `Enter`, `Control+Enter` |
| `scroll` | `to` (a target) or `by_pixels`, `duration_ms` | eased, so it reads as a scroll on video |
| `wait`, `wait_for` | `ms`; `target`, `state`, `timeout_ms` | |
| `mark` | `label` | records the time in the video, to trim and zoom to later |
| `screenshot` | `path`, `full_page` | `.png` or `.jpg` in the workspace |

A `target` is what `inspect_page` returned (`{role, name}`, `{text}` or `{selector}`, plus `nth`). One that matches no
element fails with `not_found`; one that matches several fails with `ambiguous_target` instead of clicking the first.

The first failing step stops the run and the rest are reported `skipped`. The response is then `status: "partial"` with a
`failure`: the step's `error_code` (`not_found`, `ambiguous_target`, `not_actionable`, `timeout`, `navigation_failed`,
`workspace_error`), the page as it was (`page`, the same shape as an inspection) and up to 10 `candidates`, the elements
that look like what the step meant. A recording is still saved up to that point (with a short tail while the page was
read). Running past `max_duration_seconds` (capped by `BROWSER_STUDIO_MAX_RECORD_SECONDS`, default `180`) fails the
current step with `timeout` the same way.

`rehearse: true` runs the same steps with no video, no cursor and waits capped at 500 ms, so a long list is checked in
seconds. **A rehearsal acts for real**: it clicks and types on the live page, because later steps depend on what earlier
ones did. `output_path` is required (a `.webm`) only when recording.

Each step reports when it ran (`started_at_seconds`, `ended_at_seconds`, on the video's clock) and, if it acted on an
element (or scrolled to one), its `box` as fractions of the viewport: the centre of it is the focus for a zoom. `markers`
list each `mark`, and the runner adds `ready`, the time the page had loaded, as the place to start a clip. Marker times
were checked against the video's own frames (a page flashing red at a known moment) and agree to about 50 ms. The
`output` gives the path, size and duration; the file is cut to end with the last step (the browser films on for about a
second after it), by a stream copy that is checked and falls back to the original.

The browser only records frames when a page repaints, and on a still page its recorder could stop early and lose
everything after. Recordings therefore carry a hidden pixel that changes by 1/255 of brightness (`studio/keepalive.js`);
20 of 20 recordings were complete with it, and about 3 in 10 were not without.

A page that needs `scroll` before content exists (loaded on scroll) must be scrolled before it is targeted.

Recording uses Playwright's own ffmpeg, which `playwright install --only-shell chromium` already installs. Walkthroughs
and inspections share one slot (`BROWSER_STUDIO_CONCURRENCY`, default `1`), separate from page rendering. The request
stays open for the whole run, so a client's timeout must be longer than `max_duration_seconds` plus about 30 seconds.

## Scenes

`POST /v1/browser/scenes` renders an animated scene to a video: `{request_id, workspace_id, template + params | scene_path,
output_path, duration_seconds, fps, viewport, transparent}`. Either a built-in `template` with `params`
(`heading`, `subheading`, `eyebrow`, `footer`, `accent`, `theme`) so an agent sends a few words and not a page of HTML, or
`scene_path`, the agent's own `.html` in the workspace.

| Template | For |
| --- | --- |
| `title` | an opening or section card: eyebrow, heading, accent bar, subheading |
| `outro` | a closing card with a call to action pill (`footer`) |
| `lower_third` | a caption laid over footage; transparent, so it must be a `.webm` |

Rendering is frame by frame, not in real time: the clock is stopped, every CSS animation is paused and moved to the time of
the frame, the frame is captured, and only then does time move on. The same scene gives the same frames however busy the
runner is (a test renders twice and compares). Animate with CSS animations or the Web Animations API; a custom page can set
`window.__studioReady` to a promise to hold the first frame until its data has loaded.

A custom page's relative URLs load from the workspace (`https://scene.studio.invalid/<path>`, which can never resolve to a
real host): only web assets (html, css, js, json, svg, images, fonts), never outside the workspace, never through a symlink.
Every other address goes through the same public-internet-only guard as everything else the browser does. A 3 second scene
takes about 3 seconds to render.

## Compositions

`POST /v1/media/compositions` turns clips, scenes and overlays into one video. The timeline is data, and `media/compose.py`
turns it into an ffmpeg filter graph with a pure function: nothing a caller writes reaches ffmpeg as text (names come from an
allowlist, the rest are numbers), inputs can only be files, and the graph goes in a script file, not on the command line.

- **`clips`** (in order): `source` (a video or image in the workspace), `start`, `end`, `speed`, `hold_seconds` (images),
  `fit` (`cover` or `contain`), `zoom` and `transition_in`.
- **`zoom`**: keyframes `{at, duration, x, y, scale, ease}` eased into one smooth move, `at` against the clip as cut.
  Copy `x` and `y` from the box a walkthrough step reported.
- **`transition_in`**: `fade`, `fadeblack`, `dissolve`, `wipeleft`, `wiperight`, `slideleft`, `slideright`, `smoothleft` or
  `circleopen`, with a `duration`. Leave it out for a hard cut.
- **`overlays`**: a transparent scene or image, with `clip` (which clip it belongs to) and `at` (seconds after that clip begins
  in the finished video), so no one adds up transitions. `x`, `y` and `width` are fractions of the frame.
- **`audio`**: a bed with `volume`, `fade_in` and `fade_out`, trimmed to the video.
- **`output`**: `.mp4` (H.264, AAC) or `.webm`, 1280x720 at 30 fps by default, up to 1920x1080.

The length is capped by `MEDIA_COMPOSE_MAX_SECONDS` (default `300`) before ffmpeg starts, a compose that runs past
`MEDIA_COMPOSE_TIMEOUT_SECONDS` (default `300`) is killed with its whole process group, and composes run one at a time
(`MEDIA_COMPOSE_CONCURRENCY`). The response is `{output, duration_seconds}`.

`POST /v1/media/probes` reads a file's `duration_seconds`, size, `fps` and `has_audio`, and can save one frame
(`frame_at_seconds` + `frame_path`) or a contact sheet of six evenly spaced frames in one image (`sheet_path`), which is the
cheapest way to check a finished video.

ffmpeg and ffprobe come from the image's package (`apt-get install ffmpeg`): Playwright's own ffmpeg only encodes VP8.
Locally, install them (`brew install ffmpeg`); the tests that need them skip themselves without.

## Hosted stdio MCP servers

The runner hosts stdio MCP servers as long-lived processes and exposes each one through a stateless Streamable HTTP
façade, so the API talks to them with its ordinary MCP client. It only runs packages baked into the image:

```
mcp_packages/<key>/
  package.toml       entrypoint = "<console script>"   (optional: args = [...])
  requirements.txt   pinned, reviewed install (a git dependency pins a commit, never a branch)
```

The `mcp-packages` build stage installs each package into `/opt/mcp/<key>`; `git` exists only in that stage. Adding or
upgrading a package is a code review plus a redeploy. Nothing is installed at runtime.

- `PUT /v1/mcp/servers/{server_id}` with `{spec: {package, args, env, files}, wait_seconds}` is idempotent: it keeps a
  running server whose spec fingerprint matches, drains and restarts it when the spec changes (for example rotated
  credentials), and starts it when missing (after a redeploy, idle reap, or crash).
- `files` maps an env name to file content. Each file is written `0600` under the server's private `secrets/`
  directory, the env var holds its path, and the directory is removed when the server stops.
- The façade answers `initialize` from the child's cached handshake (a stdio process accepts one), remaps request ids
  so concurrent callers cannot collide, and refuses server-to-client requests with `-32601`.
- Servers idle for 15 minutes are stopped; at 8 running servers the least recently used idle one is evicted.

The process pool lives in memory, so **run this service as one replica with one worker** (the `CMD` sets no
`--workers`). All hosted servers share the `runner` uid, which is why only reviewed, baked packages may run.

On Apple Silicon machines whose CPU reports SME (M4-class), the arm64 `cryptography` wheel used by some Python MCP
packages crashes with an illegal instruction inside Docker. Build or run the image with `--platform linux/amd64`
locally if a hosted server exits with code `-4`; Railway builds for amd64.

## Python executions

Python executions accept script and `requirements.txt` content directly. Callers select from fixed operations rather than supplying executable paths or a working directory:

```json
{
  "request_id": "tooljob_or_run_node_id",
  "script": "import httpx\nprint(httpx.__version__)",
  "requirements": "httpx==0.28.1",
  "commands": [
    {"operation": "install_requirements"},
    {"operation": "run_script", "args": []}
  ],
  "timeout_seconds": 60
}
```

The runner creates a private UUID run directory, writes fixed `script.py` and `requirements.txt` paths there, and uses `uv` to create a fresh `.venv` before every execution. Requirements are installed into that environment and the script always runs with its Python interpreter. When the API supplies an opaque `workspace_id`, the script runs in that conversation workspace so generated reports remain available through the File System skill. The private run directory and environment are cleaned afterward.

Environment creation is returned as the non-agent-controllable first command result with `operation: "create_environment"`. The remaining ordered command list is fail-fast: after setup or a requested command fails or times out, later entries are returned with `status: "skipped"`. The 60-second default is a single deadline shared by environment creation, dependency installation, and script execution.

Requirements are limited to package-index requirement specifiers and binary wheels. Options, nested requirement files, local paths, direct URLs, and source distributions are rejected. Binary-extension packages such as NumPy are supported when a compatible wheel is available. Python receives a sanitized environment and a startup audit policy that rejects normal filesystem writes outside its run directory and prevents child-process execution. The production container also runs the service as an unprivileged user. This is controlled script execution, not unrestricted shell or host isolation.

The operation-to-argv mapping in `CliRunnerService._python_command_argv` is the policy extension point for future project-scoped `uv` support. Any future operations must remain typed and allowlisted; do not expose arbitrary `uv` argv or general shell execution.

The API remains responsible for user identity, skill installation, command policy validation, STS credential generation, large-output paging, and future analytics.

## Filesystem workspaces

`POST /v1/filesystem/actions` accepts typed action names and structured arguments. It never accepts host paths or shell commands. The sidecar canonicalizes every workspace-relative path, blocks traversal and symlink escapes, bounds reads/search/diffs, detects binary files, applies text writes atomically, enforces per-write and workspace quotas, and returns a compact structured result.

`GET /v1/filesystem/files?workspace_id=…&path=…` streams one existing workspace file of any type (same bearer token and path rules; a symlink or a path outside the workspace is refused). The API uses it to turn a finished video into an artifact.

Workspaces default to `/tmp/infra-cli-runner/workspaces`. The root and limits can be configured with `FILE_SYSTEM_WORKSPACE_ROOT`, `FILE_SYSTEM_MAX_READ_BYTES`, `FILE_SYSTEM_MAX_WRITE_BYTES`, and `FILE_SYSTEM_WORKSPACE_QUOTA_BYTES`. A workspace that no request has touched for `FILE_SYSTEM_WORKSPACE_TTL_SECONDS` (default 3600; 0 keeps them) is deleted whole by a sweeper that runs every five minutes, so finished videos and recordings don't pile up. Each request to a workspace refreshes a marker under `<root>/.last-used/`, kept outside the workspace so it never shows in a listing or counts against the quota. The runner executes validated filesystem requests as received; authorization and approval policy belong to the API skill platform.

Run locally:

```bash
uv sync
CLI_RUNNER_SHARED_TOKEN=dev-token uv run uvicorn main:app --reload
```

Run tests:

```bash
uv run python -m unittest discover -s tests -v
```

`tests/test_mcp_servers.py` drives a real stdio process (`tests/fake_mcp_server.py`) through the pool and façade.
