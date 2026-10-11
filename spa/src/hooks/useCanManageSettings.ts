import { useEffect, useState } from "react";
import { settingsAccessService } from "../services/settings/SettingsAccessService";

/**
 * Whether to offer the controls that change the account's settings. The API decides either way; this only
 * spares members buttons they can't use. Undefined while loading, and true if the check itself fails.
 */
export function useCanManageSettings(): boolean | undefined {
  const [canManage, setCanManage] = useState<boolean>();

  useEffect(() => {
    settingsAccessService
      .get()
      .then((access) => setCanManage(access.can_manage))
      .catch(() => setCanManage(true));
  }, []);

  return canManage;
}
