import { useEffect, useState } from "react";
import { Building2 } from "lucide-react";
import { Pill, Select, SelectContent, SelectItem, SelectTrigger } from "../ui";
import { accountService, type AccessSummary, type AccountMembership } from "../../services/accounts";
import { setActiveAccountId } from "../../services/http";
import "./AccountSwitcher.css";

const ACCESS_LABELS: Record<AccessSummary, string> = { owner: "Owner", admin: "Admin", member: "Member" };

/**
 * The account every request acts in, shown in the dashboard header on every page. Switching reloads
 * the dashboard, so nothing fetched for the previous account stays on screen.
 */
export function AccountSwitcher() {
  const [accounts, setAccounts] = useState<AccountMembership[]>([]);
  const [current, setCurrent] = useState<AccountMembership>();
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    accountService
      .list()
      .then((listed) => {
        const chosen = accountService.current(listed);
        // Pin this tab to its account, so a switch on another device doesn't move it mid-session
        setActiveAccountId(chosen?.account_id ?? null);
        setAccounts(listed.filter((account) => account.membership_status === "active"));
        setCurrent(chosen);
      })
      .catch(() => setAccounts([]));
  }, []);

  if (!current) {
    return null;
  }

  const switchTo = async (accountId: string) => {
    if (accountId === current.account_id) {
      return;
    }
    setSwitching(true);
    try {
      await accountService.switchTo(accountId);
      window.location.assign("/dashboard");
    } catch {
      setSwitching(false);
    }
  };

  return (
    <Select value={current.account_id} onValueChange={switchTo} disabled={switching || accounts.length < 2}>
      <SelectTrigger className="account-switcher" aria-label="Switch account">
        <Building2 className="account-switcher__icon" aria-hidden />
        <span className="account-switcher__name" title={current.name}>{current.name}</span>
        <Pill size="sm" variant="secondary" className="account-switcher__role">{ACCESS_LABELS[current.access_summary]}</Pill>
      </SelectTrigger>
      <SelectContent align="start">
        {accounts.map((account) => (
          <SelectItem key={account.account_id} value={account.account_id}>
            <span className="account-switcher__option">
              <span>{account.name}</span>
              <span className="account-switcher__access">{ACCESS_LABELS[account.access_summary]}</span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
