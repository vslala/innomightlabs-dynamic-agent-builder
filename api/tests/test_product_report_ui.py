"""Offline template behavior: real embedded JS, synthetic reports, minimal DOM in Node.

This is not a layout/browser test. No backend, AWS, or network APIs are exposed to
JavaScript; unsafe HTML sinks fail immediately. Run with pytest on this file only.
"""

import csv
import io
import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

import pytest


TEMPLATE = Path(__file__).resolve().parents[1] / "scripts" / "product_report.html"
START = "2026-10-10T12:34:56.789Z"
END = "2026-10-12T08:09:10.123Z"


class TemplateParser(HTMLParser):
    """Extract IDs and scripts while checking explicit tag nesting."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.scripts: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "id" in attributes:
            identifier = attributes["id"]
            assert identifier is not None and identifier not in self.ids
            self.ids.append(identifier)
        assert not (tag in {"script", "img", "iframe", "link"} and
                    ("src" in attributes or "href" in attributes)), "External resource"
        if tag == "script":
            self.scripts.append("")
        if tag not in {"meta", "input", "br", "hr", "img", "link", "wbr"}:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.stack and self.stack.pop() == tag, f"Mismatched closing {tag}"

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1] == "script":
            self.scripts[-1] += data


NODE_HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.attributes = {}; this.dataset = {};
    this.value = ''; this._text = ''; this.open = false; this.disabled = false;
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set innerHTML(value) { throw new Error('Unsafe innerHTML'); }
  set outerHTML(value) { throw new Error('Unsafe outerHTML'); }
  append(...children) { for (const child of children) child.parent = this; this.children.push(...children); }
  replaceChildren(...children) { this._text = ''; this.children = []; this.append(...children); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  get selectedOptions() { return [{textContent: this.value}]; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  click() { if (!this.disabled) { this.onclick?.(); this.parent?.click(); } }
  remove() {}
}
const nodes = new Map(input.ids.map(id => [id, new Element()]));
const $ = id => nodes.get(id);
$('report-data').textContent = JSON.stringify(input.report);
// Initial values of native selects in the template; native input values start empty.
$('audience').value = 'all'; $('page-size').value = '25'; $('theme').value = 'system';
let download, revoked = false;
const document = {
  getElementById: $, createElement: tag => new Element(tag),
  createElementNS: (_, tag) => new Element(tag), body: new Element('body'),
  documentElement: new Element('html'),
  write() { throw new Error('Unsafe document.write'); }
};
const context = vm.createContext({document, Blob, URL: {
  createObjectURL(blob) { download = blob; return 'blob:offline-test'; },
  revokeObjectURL() { revoked = true; }
}, setTimeout: callback => callback()});
vm.runInContext(input.script, context, {timeout: 3000});
const metrics = () => Object.fromEntries($('metrics').children.map(card =>
  [card.children[0].textContent, card.children[1].textContent]));
const rolling = () => $('rolling').children.map(card => card.children[1].textContent);
const rows = () => $('users-body').children;
const headers = () => $('columns').children;
const column = title => headers().findIndex(header =>
  header.children[0].textContent.replace(/ [↑↓]$/, '') === title);
const cell = (row, title) => row.children[column(title)].textContent;
const sort = title => headers()[column(title)].children[0].click();
const search = value => { $('search').value = value; $('search').oninput(); };
const audience = value => { $('audience').value = value; $('audience').onchange(); };
const date = (id, value) => { $(id).value = value; $(id).onchange(); };
(async () => {
  const checks = new Function('$', 'assert', 'metrics', 'rolling', 'rows', 'cell',
    'sort', 'search', 'audience', 'date', 'getDownload', 'isRevoked', 'document',
    'return (async () => {' + input.checks + '})()');
  const result = await checks($, assert, metrics, rolling, rows, cell, sort,
    search, audience, date, () => download, () => revoked, document);
  process.stdout.write(JSON.stringify(result ?? null));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.fixture(scope="module")
def run_ui() -> Callable[[dict, str], object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the standalone report UI tests")
    source = TEMPLATE.read_text(encoding="utf-8")
    parser = TemplateParser()
    parser.feed(source)
    assert not parser.stack
    assert len(parser.scripts) == 2
    assert parser.scripts[0] == "__REPORT_DATA__"
    assert source.count("__REPORT_DATA__") == 1

    def run(report: dict, checks: str) -> object:
        completed = subprocess.run(
            [node, "-e", NODE_HARNESS],
            input=json.dumps({"ids": parser.ids, "script": parser.scripts[1],
                              "report": report, "checks": checks}),
            text=True, capture_output=True, timeout=10, check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
        return json.loads(completed.stdout)

    return run


@pytest.fixture
def report() -> dict:
    def event(at: str, kind: str = "message_sent", interactive: bool = True) -> dict:
        return {"at": at, "kind": kind, "interactive": interactive, "agent_id": "<b>agent</b>"}

    def user(identifier: str, audience: str, signup: str | None, events: list[dict]) -> dict:
        return {"id": identifier, "audience": audience, "name": identifier,
                "email": f"{identifier}@example.test", "signup": signup,
                "status": "enabled", "events": events}

    return {
        "meta": {"start": START, "end": END, "generated_at": END,
                 "table": "offline-fixture", "region": "test-region",
                 "scan": {"pages": 1, "scanned": 42, "capacity": 2.5},
                 "warnings": ["<img onerror=evil>"]},
        "inventory": {"Agent": 2}, "quality": {"missing_signup": 1},
        "users": [
            user("alpha", "platform", START, [
                event("2026-10-10T12:34:56.788Z"), event(START),
                event("2026-10-10T18:00:00Z"), event("2026-10-11T00:00:00Z"),
                event("2026-10-11T02:00:00Z", "automation_run", False), event(END),
            ]),
            user("quiet", "platform", END, [event("2026-10-11T03:00:00Z", "automation_run", False)]),
            user("old", "platform", None, [event("2026-09-12T08:09:10.123Z")]),
            user("outside", "platform", "2026-10-10T12:34:56.788Z", []),
            user("guest", "widget_guest", START, [event("2026-10-12T08:09:10.122Z")]),
            user("google", "widget_google", START, [event("2026-10-05T00:00:00Z")]),
            *[user(f"idle{i:02}", "platform", None, []) for i in range(26)],
        ],
    }


def test_startup_metrics_and_safe_text(run_ui: Callable, report: dict) -> None:
    run_ui(report, r"""
assert.equal($('error').textContent, '');
assert.deepEqual(metrics(), {'Platform signups':'1', 'Active platform':'1', 'Active visitors':'1', 'Messages sent':'4'});
assert.equal($('retained-platform').textContent, '30');
assert.deepEqual(rolling(), ['1', '2', '4']);
assert.equal($('warnings').children[0].textContent, '<img onerror=evil>');
assert.equal($('inventory').textContent, 'Agent2');
assert.equal($('quality').textContent, 'Missing Signup1');
assert.match($('daily-chart').children[0].attributes['aria-label'], /2026-10-10: 1 signups, 1 active/);
assert.match($('feature-chart').children[0].attributes['aria-label'], /Automation Run: 2/);
$('theme').value = 'dark'; $('theme').onchange();
assert.equal(document.documentElement.dataset.theme, 'dark');
$('theme').value = 'system'; $('theme').onchange();
assert.equal(document.documentElement.dataset.theme, undefined);
""")


def test_empty_report_startup(run_ui: Callable, report: dict) -> None:
    report.update(users=[], inventory={}, quality={})
    report["meta"]["warnings"] = []
    run_ui(report, r"""
assert.equal($('error').textContent, '');
assert.ok(Object.values(metrics()).every(value => value === '0'));
assert.equal($('retained-platform').textContent, '0');
assert.deepEqual(rolling(), ['0','0','0']);
assert.match(rows()[0].textContent, /No identities match/);
assert.equal($('previous').disabled, true); assert.equal($('next').disabled, true);
assert.match($('feature-chart').textContent, /No observed events/);
assert.match($('warnings').textContent, /No scan warnings/);
$('export').click(); assert.ok(await getDownload().text());
""")


def test_precise_boundaries_narrowing_and_reset(run_ui: Callable, report: dict) -> None:
    run_ui(report, r"""
assert.match($('range-note').textContent, /2026-10-10T12:34:56.789Z/);
assert.match($('range-note').textContent, /2026-10-12T08:09:10.123Z/);
search('alpha'); assert.equal(cell(rows()[0], 'Messages'), '3');
assert.equal(cell(rows()[0], 'Events'), '4'); assert.equal(cell(rows()[0], 'Active days · UTC'), '2');
const before = rolling();
date('from', '2026-10-11');
assert.deepEqual(metrics(), {'Platform signups':'0', 'Active platform':'1', 'Active visitors':'1', 'Messages sent':'2'});
assert.equal(cell(rows()[0], 'Active days · UTC'), '1'); assert.equal(cell(rows()[0], 'Events'), '2');
date('through', '2026-10-11'); assert.equal(metrics()['Messages sent'], '1');
assert.match($('range-note').textContent, /2026-10-12T00:00:00.000Z/);
assert.deepEqual(rolling(), before); assert.equal($('retained-platform').textContent, '30');
const validNote = $('range-note').textContent;
date('through', '2026-10-10'); assert.match($('error').textContent, /valid, non-empty/);
assert.equal($('range-note').textContent, validNote);
date('from', ''); assert.match($('error').textContent, /valid, non-empty/);
$('reset').click(); assert.equal($('error').textContent, '');
assert.equal(metrics()['Messages sent'], '4'); assert.equal(cell(rows()[0], 'Active days · UTC'), '2');
""")


def test_audience_and_search_only_filter_table_and_csv(run_ui: Callable, report: dict) -> None:
    run_ui(report, r"""
search('ALPHA@EXAMPLE.TEST'); assert.equal(rows().length, 1);
assert.equal(metrics()['Messages sent'], '4');
audience('widget'); assert.equal(metrics()['Messages sent'], '1');
assert.equal(metrics()['Platform signups'], '0'); assert.match(rows()[0].textContent, /No identities match/);
search(''); assert.equal(rows().length, 2); assert.deepEqual(rolling(), ['1','1','2']);
assert.equal($('retained-platform').textContent, '30');
audience('platform'); assert.equal(metrics()['Active visitors'], '0');
assert.equal(metrics()['Messages sent'], '3'); assert.deepEqual(rolling(), ['0','1','2']);
search('quiet'); assert.equal(cell(rows()[0], 'Activity'), 'Quiet');
assert.equal(cell(rows()[0], 'Active days · UTC'), '0'); assert.equal(cell(rows()[0], 'Events'), '1');
search('old'); assert.equal(cell(rows()[0], 'Activity'), 'No observed activity');
search('enabled'); assert.match($('page-note').textContent, /30 identities/);
""")


def test_sort_paging_and_details(run_ui: Callable, report: dict) -> None:
    run_ui(report, r"""
assert.equal(rows().length, 25); assert.equal($('previous').disabled, true);
$('next').click(); assert.equal(rows().length, 7); assert.equal($('next').disabled, true);
$('previous').click(); assert.equal(rows().length, 25);
$('page-size').value = '10'; $('page-size').onchange(); assert.equal(rows().length, 10);
sort('Identity'); assert.match(rows()[0].children[0].textContent, /^alpha/);
sort('Identity'); assert.match(rows()[0].children[0].textContent, /^quiet/);
sort('Events'); sort('Events'); assert.equal(cell(rows()[0], 'Events'), '4');
sort('Active days · UTC'); sort('Active days · UTC'); assert.equal(cell(rows()[0], 'Active days · UTC'), '2');
search('alpha'); rows()[0].click(); assert.equal($('details').open, true);
assert.equal($('kind-counts').textContent, 'Message Sent3Automation Run1');
assert.equal($('timeline').children.length, 4);
assert.equal($('timeline').children[0].children[0].dateTime, '2026-10-11T02:00:00.000Z');
assert.match($('timeline').textContent, /Automated \/ non-interactive/);
assert.match($('timeline').textContent, /<b>agent<\/b>/);
$('close-details').click(); assert.equal($('details').open, false);
search('old'); rows()[0].children[0].children[0].click();
assert.match($('timeline').textContent, /does not imply never used/);
""")


@pytest.mark.parametrize("formula", ["=1+1", "+SUM(1)", "-1", "@evil", " \t=1", "\ttext", "\rtext", "\ntext"])
def test_filtered_csv_formula_safety(run_ui: Callable, report: dict, formula: str) -> None:
    report["users"][0].update(name=formula, email='quoted,"email"\n@example.test')
    report["users"][0]["status"] = formula
    result = run_ui(report, r"""
search('alpha'); $('export').click();
assert.equal(isRevoked(), true);
return await getDownload().text();
""")
    records = list(csv.DictReader(io.StringIO(str(result).lstrip("\ufeff"))))
    assert len(records) == 1
    row = records[0]
    assert row["Name"] == "'" + formula
    assert row["Account status"] == "'" + formula
    assert row["Email"] == 'quoted,"email"\n@example.test'
    assert row["Messages"] == "3"
    assert row["Active days UTC"] == "2"
    assert row["Events"] == "4"
    assert row["Window start inclusive"] == START
    assert row["Window end exclusive"] == END
