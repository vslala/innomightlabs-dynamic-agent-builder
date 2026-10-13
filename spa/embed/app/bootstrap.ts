import type { ImageInputAvailability } from "../../packages/image-attachments/src";

/** What the API's /embed/{public_key} shell inlines into the page for the app. */
export interface Bootstrap {
  public_key: string;
  agent_id: string;
  agent_name: string;
  agent_description: string | null;
  api_base_url: string;
  /** Whether visitors may attach images, and the limits to check them against. */
  image_input?: ImageInputAvailability;
  allow_guests: boolean;
  guest_session_timeout_minutes?: number;
}

export function readBootstrap(doc: Document = document): Bootstrap {
  const element = doc.getElementById("innomight-bootstrap");
  if (!element?.textContent) {
    throw new Error("Missing #innomight-bootstrap; the chat app must be loaded by the /embed shell.");
  }
  const bootstrap = JSON.parse(element.textContent) as Bootstrap;
  return { ...bootstrap, allow_guests: bootstrap.allow_guests === true };
}
