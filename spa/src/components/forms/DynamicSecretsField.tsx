import { useMemo } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
// Label rendered by FormField
import type { FormValue } from "../../types/form";

export type SecretPair = { name: string; value: string };

function asSecretPairs(value: FormValue): SecretPair[] {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value
      .filter((v): v is any => typeof v === "object" && v !== null)
      .map((v) => ({ name: String((v as any).name || ""), value: String((v as any).value || "") }));
  }
  return [];
}

export function DynamicSecretsField({
  value,
  onChange,
}: {
  value: FormValue;
  onChange: (value: FormValue) => void;
}) {
  const pairs = useMemo(() => asSecretPairs(value), [value]);

  const update = (next: SecretPair[]) => {
    // Keep even empty names/values? We’ll filter empties on submit in backend too,
    // but keep them here for UX as user types.
    onChange(next);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
        Add secret variables referenced by <code>{"{{secret:NAME}}"}</code> inside your manifest.
      </p>

      {pairs.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>No secrets added.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {pairs.map((p, idx) => (
            <div
              key={`${idx}`}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1.5fr auto",
                gap: "0.5rem",
                alignItems: "center",
              }}
            >
              <Input
                value={p.name}
                placeholder="name (e.g. wp_token)"
                onChange={(e) => {
                  const next = [...pairs];
                  next[idx] = { ...next[idx], name: e.target.value };
                  update(next);
                }}
              />
              <Input
                value={p.value}
                placeholder="value"
                type="password"
                onChange={(e) => {
                  const next = [...pairs];
                  next[idx] = { ...next[idx], value: e.target.value };
                  update(next);
                }}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  const next = pairs.filter((_, i) => i !== idx);
                  update(next);
                }}
              >
                Remove
              </Button>
            </div>
          ))}
        </div>
      )}

      <div>
        <Button
          type="button"
          onClick={() => update([...pairs, { name: "", value: "" }])}
          variant="secondary"
        >
          Add secret
        </Button>
      </div>
    </div>
  );
}
