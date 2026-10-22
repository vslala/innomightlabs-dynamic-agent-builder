"""Tells an agent what is on a page, so the steps it writes use targets that exist.

Raw HTML is too big to read and guessed selectors break, so the page is reduced to two things: an accessibility
outline for the overview, and an inventory of what a person could act on, each with a target the runner has already
checked points at exactly that element. The inventory script in `inventory.js` only reports; the targets are proposed
and verified here, with the real Playwright locators a recording will use later.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from playwright.async_api import Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeout

from src.infra_cli_runner.browser import BrowserRenderer, RenderError
from src.infra_cli_runner.filesystem import FileSystemService
from src.infra_cli_runner.studio.models import (
    Box,
    InspectRequest,
    InspectResponse,
    PageElement,
    PageSnapshot,
    Section,
)
from src.infra_cli_runner.studio.steps import StepRun, check_step_paths, run_steps
from src.infra_cli_runner.studio.targets import Candidate, verified_target

INVENTORY_JS = Path(__file__).with_name("inventory.js").read_text(encoding="utf-8")
MAX_OUTLINE_BYTES = 12 * 1024
MAX_SECTIONS = 40
NAME_LIMIT = 60
#: A page that keeps growing as it is scrolled (infinite feeds) is only followed this far.
MAX_SCROLL_STEPS = 30
INSPECT_SCREENSHOT_SUFFIXES = frozenset({".png"})
SCROLL_TO = "y => window.scrollTo({top: y, behavior: 'instant'})"
PAGE_HEIGHT = "Math.max(document.documentElement.scrollHeight, window.innerHeight)"
ANNOTATE_JS = """marks => {
  const layer = document.createElement('div');
  layer.id = '__studio_annotations';
  layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647';
  for (const mark of marks) {
    const box = document.createElement('div');
    box.style.cssText = `position:absolute;left:${mark.x}px;top:${mark.y}px;width:${mark.width}px;height:${mark.height}px;` +
      'outline:2px solid #e11d48;';
    const label = document.createElement('span');
    label.textContent = mark.id;
    label.style.cssText = 'position:absolute;left:0;top:0;background:#e11d48;color:#fff;font:700 11px sans-serif;padding:1px 3px;';
    box.appendChild(label);
    layer.appendChild(box);
  }
  document.documentElement.appendChild(layer);
}"""
REMOVE_ANNOTATIONS_JS = "() => document.getElementById('__studio_annotations')?.remove()"


async def inspect_page(renderer: BrowserRenderer, files: FileSystemService, request: InspectRequest) -> InspectResponse:
    workspace = files.workspace(request.workspace_id)
    check_step_paths(files, workspace, request.steps)
    try:
        async with asyncio.timeout(request.timeout_seconds + 15):
            async with renderer.studio_page(
                width=request.viewport.width, height=request.viewport.height, timeout_seconds=request.timeout_seconds
            ) as page:
                return await _inspect(page, files, workspace, request)
    except TimeoutError as exc:
        raise RenderError("the browser took too long") from exc
    except PlaywrightError as exc:
        raise RenderError(f"couldn't read the page: {str(exc).splitlines()[0]}") from exc


async def _inspect(page: Page, files: FileSystemService, workspace: Path, request: InspectRequest) -> InspectResponse:
    timeout_ms = request.timeout_seconds * 1000
    try:
        await page.goto(request.url, wait_until="domcontentloaded", timeout=timeout_ms)
    except PlaywrightError as exc:
        raise RenderError(f"couldn't load the page: {str(exc).splitlines()[0]}") from exc
    await _settle(page, timeout_ms / 2)
    timings = []
    if request.steps:
        # A step that fails stops the rest, but the page as far as it got is still what the caller asked to see.
        run = StepRun(page, files, workspace, rehearse=True, step_timeout_seconds=request.timeout_seconds / 2)
        timings = (await run_steps(run, request.steps)).timings
    if request.scroll_through:
        await _scroll_through(page, request.viewport.height)
    await page.evaluate(SCROLL_TO, 0)

    reading = await read_page(
        page,
        roles=request.roles,
        query=request.query,
        max_elements=request.max_elements,
        max_heading_level=request.max_heading_level,
        outline_bytes=MAX_OUTLINE_BYTES if request.include_outline else 0,
    )
    if request.annotate:
        await page.evaluate(ANNOTATE_JS, _marks(reading.snapshot.elements, reading.page_width, reading.page_height))
    image = await page.screenshot(type="png")
    await page.evaluate(REMOVE_ANNOTATIONS_JS)
    screenshot = files.write_output(
        workspace, request.screenshot_path or f"inspect/{uuid4().hex[:8]}.png", image, suffixes=INSPECT_SCREENSHOT_SUFFIXES
    )
    fields = {name: getattr(reading.snapshot, name) for name in PageSnapshot.model_fields}
    return InspectResponse(**fields, screenshot=screenshot, steps=timings)


@dataclass
class PageReading:
    snapshot: PageSnapshot
    page_width: int
    page_height: int


async def read_page(
    page: Page,
    *,
    roles: Sequence[str] = (),
    query: str | None = None,
    max_elements: int = 80,
    max_heading_level: int = 2,
    outline_bytes: int = MAX_OUTLINE_BYTES,
) -> PageReading:
    """The page as it is now: its outline, what can be acted on (with verified targets) and where its sections start."""
    inventory = await page.evaluate(INVENTORY_JS)
    candidates = [(item, Candidate(item)) for item in inventory["items"]]
    elements, truncated = await _elements(page, candidates, roles, query, max_elements)
    sections = await _sections(page, candidates, max_heading_level)
    outline = await page.locator("body").aria_snapshot() if outline_bytes else None
    snapshot = PageSnapshot(
        final_url=page.url,
        title=inventory["title"],
        page_height_px=inventory["page_height"],
        outline=_cut(outline, outline_bytes) if outline is not None else None,
        elements=elements,
        sections=sections,
        truncated=truncated,
    )
    return PageReading(snapshot, inventory["page_width"], inventory["page_height"])


async def _settle(page: Page, timeout_ms: float) -> None:
    # A page that keeps polling never goes idle; what has painted by the deadline is still worth reading.
    with suppress(PlaywrightTimeout):
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)


async def _scroll_through(page: Page, viewport_height: int) -> None:
    """Scrolls to the bottom a screenful at a time, so content that loads on scroll is on the page before we look."""
    position = 0
    for _ in range(MAX_SCROLL_STEPS):
        position += viewport_height
        await page.evaluate(SCROLL_TO, position)
        await page.wait_for_timeout(150)
        if position >= await page.evaluate(PAGE_HEIGHT):
            break
    await page.evaluate(SCROLL_TO, 0)
    await page.wait_for_timeout(150)
    await _settle(page, 2000)


async def _elements(
    page: Page, candidates: list[tuple[dict, Candidate]], roles: Sequence[str], query: str | None, max_elements: int
) -> tuple[list[PageElement], bool]:
    wanted = [
        (item, candidate)
        for item, candidate in candidates
        if item["kind"] == "element"
        and (not roles or item["role"] in roles)
        and (not query or query.lower() in item["name"].lower())
    ]
    wanted.sort(key=lambda pair: (not pair[0]["in_first_viewport"], pair[0]["box"]["y"], pair[0]["box"]["x"]))
    elements: list[PageElement] = []
    for item, candidate in wanted:
        if len(elements) == max_elements:
            return elements, True
        target = await verified_target(page, candidate)
        if target is None:
            continue
        elements.append(
            PageElement(
                id=f"e{len(elements) + 1}",
                role=item["role"],
                name=_short(item["name"]),
                target=target,
                y=round(item["box"]["y"], 2),
                box=Box(**item["box"]),
                in_first_viewport=item["in_first_viewport"],
                section=item["section"],
                state=item["state"] or None,
            )
        )
    return elements, False


async def _sections(page: Page, candidates: list[tuple[dict, Candidate]], max_level: int) -> list[Section]:
    sections: list[Section] = []
    for item, candidate in candidates:
        if item["kind"] != "heading" or not item["name"] or item["level"] > max_level or len(sections) == MAX_SECTIONS:
            continue
        target = await verified_target(page, candidate)
        if target is not None:
            sections.append(Section(heading=_short(item["name"]), level=item["level"], target=target, top=round(item["box"]["y"], 2)))
    return sorted(sections, key=lambda section: section.top)


def _marks(elements: list[PageElement], page_width: int, page_height: int) -> list[dict]:
    """Boxes in viewport pixels for what is in the first screen; the page is at the top when this is drawn."""
    return [
        {
            "id": element.id,
            "x": element.box.x * page_width,
            "y": element.box.y * page_height,
            "width": element.box.width * page_width,
            "height": element.box.height * page_height,
        }
        for element in elements
        if element.in_first_viewport
    ]


def _short(name: str, limit: int = NAME_LIMIT) -> str:
    """Names of whole cards and paragraphs cost an agent tokens and say nothing more than their first words."""
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def _cut(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n…[outline truncated]"
