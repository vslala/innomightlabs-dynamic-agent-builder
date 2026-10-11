import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

function sidebar(props: { open: boolean; compact: boolean }) {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={["/dashboard/agents"]}>
      <Sidebar id="nav" onClose={vi.fn()} {...props} />
    </MemoryRouter>,
  );
}

describe("primary navigation drawer", () => {
  it("keeps a closed drawer off screen and out of the tab order", () => {
    const html = sidebar({ open: false, compact: true });
    expect(html).toContain("inert");
    expect(html).not.toContain("dashboard-sidebar--open");
  });

  it("makes an open drawer reachable", () => {
    const html = sidebar({ open: true, compact: true });
    expect(html).not.toContain("inert");
    expect(html).toContain("dashboard-sidebar--open");
  });

  it("is never inert where the sidebar is always shown", () => {
    expect(sidebar({ open: false, compact: false })).not.toContain("inert");
  });

  it("marks the current section and offers a close button", () => {
    const html = sidebar({ open: true, compact: true });
    expect(html).toMatch(/href="\/dashboard\/agents"[^>]*aria-current="page"|aria-current="page"[^>]*href="\/dashboard\/agents"/);
    expect(html).toContain('aria-label="Close navigation"');
  });
});

describe("header menu button", () => {
  it("names the drawer it controls and whether it is open", () => {
    const render = (navigationOpen: boolean) => renderToStaticMarkup(
      <MemoryRouter>
        <Header title="Agents" navigationId="nav" navigationOpen={navigationOpen} onMenuClick={vi.fn()} />
      </MemoryRouter>,
    );
    expect(render(false)).toContain('aria-controls="nav"');
    expect(render(false)).toContain('aria-expanded="false"');
    expect(render(true)).toContain('aria-expanded="true"');
    expect(render(false)).toContain('aria-label="Open navigation"');
  });
});
