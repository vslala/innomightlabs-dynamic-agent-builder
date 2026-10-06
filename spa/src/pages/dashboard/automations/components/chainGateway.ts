/**
 * The server calls the chain cards make on their own.
 *
 * Cards read this from the chain context instead of importing the API service,
 * so the same cards can run against an in-memory automation (the docs tutorial)
 * as well as a saved one.
 */

import { automationApiService } from "../../../../services/automations";
import type {
  AutomationTriggerType,
  CreateAutomationTriggerRequest,
  UpdateAutomationTriggerRequest,
} from "../../../../types/automation";
import type { FormSchema } from "../../../../types/form";

export interface ChainGateway {
  /** Render a smart-value template against the latest run. */
  previewSmartValues: (template: string) => Promise<string>;
  getTriggerForm: (type: AutomationTriggerType) => Promise<FormSchema>;
  createTrigger: (request: CreateAutomationTriggerRequest) => Promise<void>;
  updateTrigger: (triggerId: string, request: UpdateAutomationTriggerRequest) => Promise<void>;
  deleteTrigger: (triggerId: string) => Promise<void>;
}

export function apiChainGateway(automationId: string): ChainGateway {
  return {
    previewSmartValues: async (template) =>
      (await automationApiService.previewSmartValues(automationId, { template })).rendered,
    getTriggerForm: (type) => automationApiService.getTriggerForm(automationId, type),
    createTrigger: async (request) => {
      await automationApiService.createTrigger(automationId, request);
    },
    updateTrigger: async (triggerId, request) => {
      await automationApiService.updateTrigger(automationId, triggerId, request);
    },
    deleteTrigger: (triggerId) => automationApiService.deleteTrigger(automationId, triggerId),
  };
}
