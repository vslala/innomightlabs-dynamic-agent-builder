import { Preferences } from "@capacitor/preferences";
import type { KeyValueStore, StorageKey } from "../types";

const KEYS: StorageKey[] = ["active_account_id", "pkce_verifier", "conversations:view"];

/**
 * Preferences (UserDefaults / SharedPreferences), which iOS does not evict the way it can a web view's
 * localStorage. Reads come from memory, loaded once by `load()`; writes go through in the background.
 */
export function createNativeStorage(): KeyValueStore & { load(): Promise<void> } {
  const values = new Map<StorageKey, string>();
  return {
    load: async () => {
      const loaded = await Promise.all(KEYS.map(async (key) => [key, (await Preferences.get({ key })).value] as const));
      for (const [key, value] of loaded) if (value !== null) values.set(key, value);
    },
    get: (key) => values.get(key) ?? null,
    set: (key, value) => {
      values.set(key, value);
      void Preferences.set({ key, value });
    },
    remove: (key) => {
      values.delete(key);
      void Preferences.remove({ key });
    },
  };
}
