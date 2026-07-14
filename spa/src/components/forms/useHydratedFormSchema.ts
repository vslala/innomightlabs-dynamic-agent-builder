import { useEffect, useMemo, useState } from "react";

import { agentApiService } from "../../services/agents/AgentApiService";
import type { FormInput, FormSchema, SelectOption } from "../../types/form";

type OptionSourceType = "agents";

const supportedOptionSources: OptionSourceType[] = ["agents"];

export function useHydratedFormSchema(schema: FormSchema): {
  schema: FormSchema;
  loading: boolean;
} {
  const requiredSources = useMemo(() => sourcesForSchema(schema), [schema]);
  const [optionsBySource, setOptionsBySource] = useState<Record<string, SelectOption[]>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const unloaded = requiredSources.filter((source) => !optionsBySource[source]);
    if (unloaded.length === 0) {
      return;
    }

    async function loadOptions() {
      setLoading(true);
      try {
        const entries = await Promise.all(
          unloaded.map(async (source) => [source, await loadSourceOptions(source)] as const)
        );
        if (!cancelled) {
          setOptionsBySource((current) => ({
            ...current,
            ...Object.fromEntries(entries),
          }));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadOptions();
    return () => {
      cancelled = true;
    };
  }, [optionsBySource, requiredSources]);

  const hydratedSchema = useMemo(
    () => ({
      ...schema,
      form_inputs: schema.form_inputs.map((field) => hydrateField(field, optionsBySource)),
    }),
    [optionsBySource, schema]
  );

  return { schema: hydratedSchema, loading };
}

function sourcesForSchema(schema: FormSchema): OptionSourceType[] {
  const sources = new Set<OptionSourceType>();
  for (const field of schema.form_inputs) {
    const source = sourceForField(field);
    if (source && !field.options?.length) {
      sources.add(source);
    }
  }
  return [...sources];
}

function sourceForField(field: FormInput): OptionSourceType | null {
  const sourceType = field.options_source?.type || field.attr?.source;
  return supportedOptionSources.includes(sourceType as OptionSourceType)
    ? (sourceType as OptionSourceType)
    : null;
}

function hydrateField(
  field: FormInput,
  optionsBySource: Record<string, SelectOption[]>
): FormInput {
  if (field.options?.length) {
    return field;
  }
  const source = sourceForField(field);
  if (!source) {
    return field;
  }
  const options = optionsBySource[source];
  return options ? { ...field, options } : field;
}

async function loadSourceOptions(source: OptionSourceType): Promise<SelectOption[]> {
  if (source === "agents") {
    const agents = await agentApiService.listAgents();
    return agents.map((agent) => ({
      value: agent.agent_id,
      label: agent.agent_name,
    }));
  }
  return [];
}
