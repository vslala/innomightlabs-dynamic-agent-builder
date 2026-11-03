import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Button } from "../../../components/ui";
import type { Capture, CapturePage } from "../../../types/leads";
import { CaptureDetail } from "./CaptureDetail";
import { CapturesPage } from "./CapturesPage";

const hooks = vi.hoisted(() => ({
  values: [] as unknown[], cursor: 0, setSearch: vi.fn(),
  selectedButton: { current: null as HTMLButtonElement | null },
}));
vi.mock("react", async (load) => ({
  ...await load<typeof import("react")>(),
  useEffect: vi.fn(),
  useMemo: (factory: () => unknown) => factory(),
  useRef: () => hooks.selectedButton,
  useState: (initial: unknown) => {
    const index = hooks.cursor++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (value: unknown) => {
      hooks.values[index] = typeof value === "function" ? value(hooks.values[index]) : value;
    }];
  },
}));
vi.mock("react-router-dom", async (load) => ({
  ...await load<typeof import("react-router-dom")>(),
  useSearchParams: () => [new URLSearchParams(), hooks.setSearch],
}));

const capture: Capture = {
  capture_id: "lead-1", account_id: "account-1", form_name: "Contact enquiry", form_inputs: [],
  answers: {}, files: [], agent_id: "agent-1", actor_kind: "visitor", actor_id: "visitor-1",
  source: "widget", status: "new", created_at: "2026-11-03T10:00:00Z",
};
const nextCapture = { ...capture, capture_id: "lead-2" };
function page() { hooks.cursor = 0; return CapturesPage(); }
function find<P>(node: React.ReactNode, matches: (element: React.ReactElement<P>) => boolean): React.ReactElement<P> | undefined {
  if (!React.isValidElement<P & { children?: React.ReactNode }>(node)) return undefined;
  if (matches(node)) return node;
  for (const child of React.Children.toArray(node.props.children)) {
    const result = find(child, matches);
    if (result) return result;
  }
}
function detail() {
  return find<React.ComponentProps<typeof CaptureDetail>>(page(), node => node.type === CaptureDetail);
}
function selectFirst() {
  const row = find<React.ComponentProps<typeof Button>>(page(), node => node.type === Button && node.props["aria-current"] === false);
  if (!row) throw new Error("Missing lead row");
  const focus = vi.fn();
  const button = { focus } as unknown as HTMLButtonElement;
  row.props.onClick?.({ currentTarget: button } as React.MouseEvent<HTMLButtonElement>);
  return focus;
}
beforeEach(() => {
  hooks.values = [
    { agents: [{ id: "agent-1", name: "Concierge" }], forms: [], statuses: [] },
    { items: [capture, nextCapture], locked_count: 0 }, false, null, null,
  ];
  hooks.selectedButton.current = null;
  hooks.setSearch.mockReset();
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { callback(0); return 1; });
});
afterEach(() => vi.unstubAllGlobals());

describe("Leads list and detail navigation", () => {
  it("starts with no selection and enables the list-first responsive layout", () => {
    expect(page().props["data-selected"]).toBe(false);
    expect(detail()).toBeUndefined();
  });

  it("opens the chosen lead without losing the loaded list", () => {
    selectFirst();
    expect(page().props["data-selected"]).toBe(true);
    expect(detail()?.props.capture).toBe(capture);
    expect(detail()?.props.agentName).toBe("Concierge");
    expect((hooks.values[1] as CapturePage).items).toEqual([capture, nextCapture]);
  });

  it("returns to the list and restores focus to the selected row", () => {
    const focus = selectFirst();
    const back = find<React.ComponentProps<typeof Button>>(page(), node => node.type === Button && React.Children.toArray(node.props.children).includes("Back to leads"));
    expect(back).toBeDefined();
    back?.props.onClick?.({} as React.MouseEvent<HTMLButtonElement>);
    expect(page().props["data-selected"]).toBe(false);
    expect(detail()).toBeUndefined();
    expect(focus).toHaveBeenCalledOnce();
    expect((hooks.values[1] as CapturePage).items).toHaveLength(2);
  });

  it("keeps the selected detail current after a status change", () => {
    selectFirst();
    detail()?.props.onChange({ ...capture, status: "won" });
    expect(detail()?.props.capture.status).toBe("won");
    expect(page().props["data-selected"]).toBe(true);
  });

  it("returns to the list after deleting the selected lead", () => {
    selectFirst();
    detail()?.props.onDelete(capture.capture_id);
    expect(page().props["data-selected"]).toBe(false);
    expect(detail()).toBeUndefined();
    expect((hooks.values[1] as CapturePage).items).toEqual([nextCapture]);
  });
});
