/** What the API's /embed/{public_key} shell inlines into the page for the app. */
export interface Bootstrap {
  public_key: string;
  agent_id: string;
  agent_name: string;
  agent_description: string | null;
  api_base_url: string;
}

export function readBootstrap(doc: Document = document): Bootstrap {
  const element = doc.getElementById("innomight-bootstrap");
  if (!element?.textContent) {
    throw new Error("Missing #innomight-bootstrap; the chat app must be loaded by the /embed shell.");
  }
  return JSON.parse(element.textContent) as Bootstrap;
}
