import { Fragment, useState } from "react";
import { Download, ExternalLink, Trash2 } from "lucide-react";
import {
  Alert,
  AlertDescription,
  Button,
  ConfirmationDialog,
  LinkButton,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../components/ui";
import { leadsApiService } from "../../../services/leads";
import type { Capture, LeadStatus } from "../../../types/leads";
import { leadsErrorMessage } from "./errors";
import { answerText, formatWhen } from "./leads";
import styles from "./Leads.module.css";

interface CaptureDetailProps {
  capture: Capture;
  agentName: string;
  statuses: LeadStatus[];
  onChange: (capture: Capture) => void;
  onDelete: (captureId: string) => void;
}

/** Everything a lead holds, by the labels its form had when it came in. Answers are shown as text, never markup. */
export function CaptureDetail({ capture, agentName, statuses, onChange, onDelete }: CaptureDetailProps) {
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const changeStatus = async (status: string) => {
    setError(null);
    try {
      onChange(await leadsApiService.updateCaptureStatus(capture.capture_id, status));
    } catch (err) {
      setError(leadsErrorMessage(err, "The status couldn't be changed."));
    }
  };

  const download = async (fileId: string) => {
    setError(null);
    try {
      window.location.assign(await leadsApiService.fileDownloadUrl(capture.capture_id, fileId));
    } catch (err) {
      setError(leadsErrorMessage(err, "The file couldn't be downloaded."));
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await leadsApiService.deleteCapture(capture.capture_id);
      onDelete(capture.capture_id);
    } catch (err) {
      setError(leadsErrorMessage(err, "The lead couldn't be deleted."));
      setConfirming(false);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <aside className={styles.panel} aria-label="Selected lead">
      <div className={styles.panelBody}>
        <div className={styles.toolbar}>
          <h3 className={styles.heading}>{capture.form_name}</h3>
          <Select value={capture.status} onValueChange={(status) => void changeStatus(status)}>
            <SelectTrigger className={styles.filter} aria-label="Status"><SelectValue /></SelectTrigger>
            <SelectContent>
              {statuses.map((status) => <SelectItem key={status.key} value={status.key}>{status.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <p className={styles.muted}>
          {agentName} · <time dateTime={capture.created_at}>{formatWhen(capture.created_at)}</time>
          {capture.source === "dashboard" && " · test lead from the dashboard"}
        </p>
        {error && <Alert variant="error"><AlertDescription>{error}</AlertDescription></Alert>}

        <dl className={styles.answers}>
          {capture.form_inputs.map((input) => (
            <Fragment key={input.name}>
              <dt>{input.label}</dt>
              <dd>{answerText(capture, input) || "—"}</dd>
            </Fragment>
          ))}
        </dl>

        {capture.files.length > 0 && (
          <div className={styles.actions}>
            {capture.files.map((file) => (
              <Button key={file.file_id} type="button" variant="outline" size="sm" onClick={() => void download(file.file_id)}>
                <Download aria-hidden="true" />{file.filename}
              </Button>
            ))}
          </div>
        )}

        <div className={styles.actions}>
          {capture.conversation_id && capture.source === "dashboard" && (
            <LinkButton to={`/dashboard/conversations/${capture.conversation_id}`} variant="outline" size="sm">
              <ExternalLink aria-hidden="true" />Conversation
            </LinkButton>
          )}
          <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(true)}>
            <Trash2 aria-hidden="true" />Delete
          </Button>
        </div>
      </div>
      <ConfirmationDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Delete this lead?"
        description="Its answers and files are removed for good. Automations that already ran on it are not undone."
        confirmText="Delete"
        variant="destructive"
        loading={deleting}
        onConfirm={remove}
      />
    </aside>
  );
}
