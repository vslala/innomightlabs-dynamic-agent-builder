import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../../components/ui";
import type { ProviderWithStatus } from "../../services/settings/ProviderSettingsService";
import { ProviderRow } from "./ProviderRow";

const provider = (overrides: Partial<ProviderWithStatus> = {}): ProviderWithStatus => ({
  provider_name: "Anthropic",
  form: { form_name: "Anthropic", submit_path: "", form_inputs: [] },
  is_configured: true,
  ...overrides,
});

function row(overrides: Partial<React.ComponentProps<typeof ProviderRow>> = {}) {
  return {
    provider: provider(),
    canManage: true,
    removing: false,
    onConfigure: vi.fn(),
    onRemove: vi.fn(),
    ...overrides,
  };
}

/** The buttons a row offers, found in the `trailing` slot it hands to ListRow. */
function buttons(props: React.ComponentProps<typeof ProviderRow>): React.ReactElement<React.ComponentProps<typeof Button>>[] {
  const trailing = (ProviderRow(props) as React.ReactElement<{ trailing: React.ReactNode }>).props.trailing;
  const found: React.ReactElement<React.ComponentProps<typeof Button>>[] = [];
  const walk = (node: React.ReactNode) => {
    if (!React.isValidElement<{ children?: React.ReactNode }>(node)) return;
    if (node.type === Button) found.push(node as React.ReactElement<React.ComponentProps<typeof Button>>);
    React.Children.forEach(node.props.children, walk);
  };
  walk(trailing);
  return found;
}

const label = (button: React.ReactElement<React.ComponentProps<typeof Button>>) => button.props.children;

describe("ProviderRow", () => {
  it("offers an admin to remove a configured provider as well as update it", () => {
    expect(buttons(row()).map(label)).toEqual(["Remove", "Update"]);
  });

  it("offers only to configure a provider that is not set up", () => {
    expect(buttons(row({ provider: provider({ is_configured: false }) })).map(label)).toEqual(["Configure"]);
  });

  it("asks to remove, and to update, when the buttons are pressed", () => {
    const props = row();
    const [remove, update] = buttons(props);

    remove.props.onClick?.({} as React.MouseEvent<HTMLButtonElement>);
    update.props.onClick?.({} as React.MouseEvent<HTMLButtonElement>);

    expect(props.onRemove).toHaveBeenCalledOnce();
    expect(props.onConfigure).toHaveBeenCalledOnce();
  });

  it("shows removal under way and stops a second press", () => {
    const [remove] = buttons(row({ removing: true }));

    expect(label(remove)).toBe("Removing...");
    expect(remove.props.disabled).toBe(true);
  });

  it("calls an OpenAI sign-in Disconnect", () => {
    const names = buttons(row({ provider: provider({ provider_name: "OpenAI" }) })).map(label);

    expect(names).toEqual(["Disconnect", "Reconnect"]);
  });

  it("gives members no buttons: their admins manage providers", () => {
    expect(buttons(row({ canManage: false }))).toEqual([]);
  });

  it("shows whether the provider is configured", () => {
    const configured = renderToStaticMarkup(<>{ProviderRow(row())}</>);
    const unset = renderToStaticMarkup(<>{ProviderRow(row({ provider: provider({ is_configured: false }) }))}</>);

    expect(configured).toContain("Configured");
    expect(unset).toContain("Not configured");
  });
});
