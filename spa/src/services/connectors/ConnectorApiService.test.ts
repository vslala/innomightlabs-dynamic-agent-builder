import { beforeEach, describe, expect, it, vi } from "vitest";

import { httpClient } from "../http/client";
import { connectorApiService } from "./ConnectorApiService";

vi.mock("../http/client", () => ({ httpClient: { delete: vi.fn() } }));

describe("connectorApiService.disconnectConnector", () => {
  beforeEach(() => vi.clearAllMocks());

  it("deletes the Google connector by its id", async () => {
    await connectorApiService.disconnectConnector("google_mail");

    expect(httpClient.delete).toHaveBeenCalledWith("/connectors/google_mail");
  });
});
