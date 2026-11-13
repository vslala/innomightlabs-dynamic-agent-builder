import { Button } from "../../components/ui";
import type { OAuthSignIn } from "../../services/settings/ProviderSettingsService";
import styles from "./Settings.module.css";

interface OAuthGuideProps {
  oauth: OAuthSignIn;
  /** The authorize URL is being fetched. */
  opening: boolean;
  onOpen: (oauth: OAuthSignIn) => void;
}

/** The steps for a provider an admin signs into, and the button that opens its sign-in. The form below takes the
 * pasted callback. */
export function OAuthGuide({ oauth, opening, onOpen }: OAuthGuideProps) {
  return (
    <div className={styles.oauthGuide}>
      <p className={styles.oauthGuideText}>{oauth.guide}</p>
      <Button type="button" variant="outline" size="sm" onClick={() => onOpen(oauth)} disabled={opening}>
        {opening ? "Opening..." : oauth.button_label}
      </Button>
    </div>
  );
}
