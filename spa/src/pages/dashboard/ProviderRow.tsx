import { AlertCircle, CheckCircle } from "lucide-react";
import { Button, ListRow } from "../../components/ui";
import { Inline } from "../../components/layout";
import type { ProviderWithStatus } from "../../services/settings/ProviderSettingsService";
import { providerActions, providerStatus, removalPrompt } from "./providerLabels";
import styles from "./Settings.module.css";

interface ProviderRowProps {
  provider: ProviderWithStatus;
  /** Only an account's admins change its providers. */
  canManage: boolean;
  /** This provider's credentials are being deleted. */
  removing: boolean;
  onConfigure: () => void;
  onRemove: () => void;
}

export function ProviderRow({ provider, canManage, removing, onConfigure, onRemove }: ProviderRowProps) {
  const { is_configured: configured } = provider;
  const actions = providerActions(provider, configured);
  return (
    <ListRow
      icon={
        configured ? (
          <CheckCircle className={styles.providerConfiguredIcon} />
        ) : (
          <AlertCircle className={styles.providerUnconfiguredIcon} />
        )
      }
      title={provider.title}
      subtitle={providerStatus(provider, configured)}
      trailing={canManage &&
        <Inline gap="xs" wrap={false}>
          {actions.remove && (
            <Button variant="outline" size="sm" onClick={onRemove} disabled={removing}>
              {removing ? removalPrompt(provider).busy : actions.remove}
            </Button>
          )}
          <Button variant={configured ? "outline" : "default"} size="sm" onClick={onConfigure}>
            {actions.configure}
          </Button>
        </Inline>
      }
    />
  );
}
