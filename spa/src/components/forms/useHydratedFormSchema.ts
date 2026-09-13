import { useEffect, useMemo, useRef, useState } from "react";

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
  // Callers commonly rebuild the schema object on every render, so this effect
  // re-runs often. Track what has already been requested rather than relying on
  // the result having landed, or a slow or failed load is retried on each render.
  const requestedSources = useRef(new Set<string>());

  useEffect(() => {
    let cancelled = false;
    const unloaded = requiredSources.filter(
      (source) => !optionsBySource[source] && !requestedSources.current.has(source)
    );
    if (unloaded.length === 0) {
      return;
    }
    unloaded.forEach((source) => requestedSources.current.add(source));

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
      } catch (error) {
        // The field renders with no options rather than retrying on every
        // render; remounting the form asks again.
        console.error("Error loading form options:", error);
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
