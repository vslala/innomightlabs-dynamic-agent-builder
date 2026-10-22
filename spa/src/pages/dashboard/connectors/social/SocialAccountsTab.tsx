import { useEffect, useState } from "react";
import { Plus, RefreshCw, Trash2 } from "lucide-react";

import { Button, ErrorState, LoadingState, StatusBadge } from "../../../../components/ui";
import { connectorApiService } from "../../../../services/connectors";
import type { SocialAccount, SocialNetwork } from "../../../../types/connectors";
import catalog from "../ConnectorCatalog.module.css";
import { ConnectorIcon } from "../ConnectorIcon";
import { returnToConnectors } from "../connectorUrls";
import { accountNote, connectionOutcome } from "./socialAccounts";
import styles from "./SocialAccountsTab.module.css";

const SOCIAL_PARAMS = ["social_oauth", "skill_oauth", "network", "social_account_ids", "reason"];

/** The member's photo, or their initial when there is none or it won't load: networks sign photo URLs and let them expire. */
function AccountAvatar({ account }: { account: SocialAccount }) {
  const [failed, setFailed] = useState(false);
  if (account.avatar_url && !failed) {
    return (
      <img
        src={account.avatar_url}
        alt=""
        className={styles.avatar}
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <span className={`${styles.avatar} ${styles.avatarFallback}`} aria-hidden="true">
      {account.display_name.charAt(0).toUpperCase()}
    </span>
  );
}

/** Connect the social accounts agents and automations post to. Admins connect; every member sees them. */
export function SocialAccountsTab({ canManage }: { canManage: boolean }) {
  const [networks, setNetworks] = useState<SocialNetwork[]>([]);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [networkData, accountData] = await Promise.all([
        connectorApiService.listSocialNetworks(),
        connectorApiService.listSocialAccounts(),
      ]);
      setNetworks(networkData);
      setAccounts(accountData);
      return networkData;
    } catch (err) {
      console.error("Error loading social accounts:", err);
      setLoadError("Failed to load social accounts. Please try again.");
      return [];
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void (async () => {
      const loaded = await load();
      // Coming back from a network's sign-in: say how it went, then clear the parameters
      const params = new URLSearchParams(window.location.search);
      const outcome = connectionOutcome(params, loaded);
      if (!outcome) return;
      SOCIAL_PARAMS.forEach((name) => params.delete(name));
      window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
      if (outcome.kind === "success") setNotice(outcome.message);
      else setError(outcome.message);
    })();
    // Runs once on mount; the OAuth return parameters are read from the URL a single time.
  }, []);

  const connect = async (network: SocialNetwork) => {
    setBusyKey(`connect:${network.key}`);
    setError(null);
    setNotice(null);
    try {
      const response = await connectorApiService.startSocialConnection(network.key, {
        return_to: returnToConnectors("social"),
      });
      window.location.href = response.authorize_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to start the ${network.display_name} sign-in.`);
      setBusyKey(null);
    }
  };

  const disconnect = async (account: SocialAccount) => {
    if (!window.confirm(`Disconnect ${account.display_name}? Agents and automations will stop posting to it.`)) return;
    setBusyKey(`disconnect:${account.social_account_id}`);
    setError(null);
    setNotice(null);
    try {
      await connectorApiService.disconnectSocialAccount(account.social_account_id);
      setAccounts((current) => current.filter((item) => item.social_account_id !== account.social_account_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect the account.");
    } finally {
      setBusyKey(null);
    }
  };

  if (loading) return <LoadingState />;
  if (loadError) return <ErrorState message={loadError} onRetry={load} />;

  const networkFor = (key: string) => networks.find((network) => network.key === key);

  return (
    <div className={catalog.catalog}>
      <p className={catalog.subtitle}>
        Connect the accounts your agents post to. An agent writes the post and its image; one click posts it to every
        connected account.
      </p>
      {error && <div className={catalog.error}>{error}</div>}
      {notice && <div className={catalog.notice}>{notice}</div>}

      <section className={styles.section}>
        <h2 className={catalog.sectionTitle}>Connect an account</h2>
        {networks.length === 0 ? (
          <p className={catalog.empty}>No social networks are set up on this server yet.</p>
        ) : (
          <div className={catalog.rows}>
            {networks.map((network) => {
              const count = accounts.filter((account) => account.network === network.key).length;
              return (
                <div key={network.key} className={catalog.row}>
                  <ConnectorIcon icon={network.icon} name={network.display_name} />
                  <div className={catalog.rowText}>
                    <div className={catalog.rowName}>{network.display_name}</div>
                    <div className={catalog.rowDescription}>{network.description}</div>
                    <div className={styles.network}>{count === 0 ? "Not connected" : `${count} connected`}</div>
                  </div>
                  {canManage && (
                    <Button
                      variant="outline"
                      size="sm"
                      className={catalog.rowAction}
                      onClick={() => void connect(network)}
                      disabled={busyKey === `connect:${network.key}`}
                    >
                      <Plus className="h-4 w-4" />
                      {busyKey === `connect:${network.key}` ? "Opening..." : count === 0 ? "Connect" : "Add another"}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <h2 className={catalog.sectionTitle}>Connected accounts</h2>
        {accounts.length === 0 ? (
          <p className={catalog.empty}>No accounts connected yet.</p>
        ) : (
          <div className={styles.accounts}>
            {accounts.map((account) => {
              const network = networkFor(account.network);
              const note = accountNote(account);
              return (
                <div key={account.social_account_id} className={catalog.row}>
                  <AccountAvatar account={account} />
                  <div className={catalog.rowText}>
                    <div className={catalog.rowName}>
                      {account.display_name}
                      <StatusBadge
                        status={account.status === "active" ? "active" : "warning"}
                        size="sm"
                        label={account.status === "active" ? "Connected" : "Needs sign-in"}
                      />
                    </div>
                    <div className={styles.network}>{network?.display_name ?? account.network}</div>
                    {note && <div className={styles.accountNote}>{note}</div>}
                  </div>
                  {canManage && (
                    <div className={styles.accountActions}>
                      {network && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void connect(network)}
                          disabled={busyKey === `connect:${network.key}`}
                        >
                          <RefreshCw className="h-4 w-4" />
                          Reconnect
                        </Button>
                      )}
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => void disconnect(account)}
                        disabled={busyKey === `disconnect:${account.social_account_id}`}
                      >
                        <Trash2 className="h-4 w-4" />
                        Disconnect
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
