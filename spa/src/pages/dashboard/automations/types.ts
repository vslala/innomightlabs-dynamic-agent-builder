import { useOutletContext } from "react-router-dom";

import type { AutomationResponse } from "../../../types/automation";

export interface AutomationDetailOutletContext {
  automation: AutomationResponse;
  reloadAutomation: () => Promise<void>;
}

export function useAutomationDetailContext(): AutomationDetailOutletContext {
  return useOutletContext<AutomationDetailOutletContext>();
}
