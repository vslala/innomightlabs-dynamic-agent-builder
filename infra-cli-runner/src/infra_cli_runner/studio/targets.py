"""Turns a `Target` into a Playwright locator, and finds targets that are sure to point at one element."""

from __future__ import annotations

from collections.abc import Callable

from playwright.async_api import Error as PlaywrightError, Locator, Page

from src.infra_cli_runner.studio.models import Target

#: The most matches `verified_target` will look through to find which one is the element it wants.
MAX_NTH_SCAN = 10
#: True when the located element is the inventory's candidate number `i`.
IS_CANDIDATE = "(el, i) => el === window.__studioCandidates[i]"


def locate(page: Page, target: Target) -> Locator:
    if target.role is not None:
        locator = page.get_by_role(target.role, name=target.name, exact=True) if target.name is not None else page.get_by_role(target.role)  # type: ignore[arg-type]
    elif target.text is not None:
        locator = page.get_by_text(target.text, exact=True)
    else:
        locator = page.locator(target.selector or "")
    return locator.nth(target.nth) if target.nth is not None else locator


def css_attribute(name: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'[{name}="{escaped}"]'


class Candidate:
    """What the inventory script reported about one element: the ingredients for a target."""

    def __init__(self, raw: dict) -> None:
        self.index: int = raw["index"]
        self.role: str = raw["role"]
        self.name: str = raw["name"]
        self.name_complete: bool = raw["name_complete"]
        self.text: str = raw["text"]
        self.test_id: str = raw["test_id"]
        self.dom_id: str = raw["dom_id"]
        self.css_path: str = raw["css_path"]


#: A long exact name is dear to repeat in every step that uses it; a short selector does the same job for less.
MAX_NAME_TARGET = 80


def _role_and_name(c: Candidate) -> Target | None:
    return Target(role=c.role, name=c.name) if c.role and c.name and c.name_complete and len(c.name) <= MAX_NAME_TARGET else None


def _test_id(c: Candidate) -> Target | None:
    return Target(selector=css_attribute("data-testid", c.test_id)) if c.test_id else None


def _element_id(c: Candidate) -> Target | None:
    return Target(selector=css_attribute("id", c.dom_id)) if c.dom_id else None


def _exact_text(c: Candidate) -> Target | None:
    return Target(text=c.text) if c.text and c.name_complete and len(c.text) <= MAX_NAME_TARGET else None


def _css_path(c: Candidate) -> Target | None:
    return Target(selector=c.css_path) if c.css_path else None


#: Most readable first. The first proposal that turns out to point at the element wins.
TARGET_PROPOSALS: list[Callable[[Candidate], Target | None]] = [_role_and_name, _test_id, _element_id, _exact_text, _css_path]


async def verified_target(page: Page, candidate: Candidate) -> Target | None:
    """A target that a walkthrough will resolve to this element: unique, or made unique with `nth`."""
    for propose in TARGET_PROPOSALS:
        target = propose(candidate)
        if target is not None and (verified := await _verify(page, target, candidate.index)) is not None:
            return verified
    return None


async def _verify(page: Page, target: Target, index: int) -> Target | None:
    try:
        matches = locate(page, target)
        count = await matches.count()
        if count == 0 or count > MAX_NTH_SCAN:
            return None
        for position in range(count):
            if await matches.nth(position).evaluate(IS_CANDIDATE, index):
                return target if count == 1 else target.model_copy(update={"nth": position})
    except PlaywrightError:
        return None
    return None
