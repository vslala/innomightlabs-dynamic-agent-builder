import { useState } from "react";
import {
  AlertBanner,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "../../components/ui";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { authService } from "../../services/auth";
import styles from "./Settings.module.css";

/**
 * Deleting the account from inside the product, which both app stores require. The person types their email
 * to confirm; the API marks them inactive at once (no more sign-ins), cancels a subscription and deletes the
 * rest in the background (`DELETE /users/me`).
 */
export function DeleteAccountCard({ email }: { email: string }) {
  const [open, setOpen] = useState(false);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Delete account</CardTitle>
        <CardDescription>
          Permanently delete your account and everything in it. An active subscription is cancelled.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="destructive" size="sm" onClick={() => setOpen(true)}>
          Delete account
        </Button>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        {/* Mounted only while open, so each opening starts empty */}
        {open && <DeleteAccountForm email={email} onCancel={() => setOpen(false)} />}
      </Dialog>
    </Card>
  );
}

function DeleteAccountForm({ email, onCancel }: { email: string; onCancel: () => void }) {
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirmed = typed.trim().toLowerCase() === email.toLowerCase();

  const deleteAccount = async () => {
    if (!confirmed || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await authService.deleteAccount();
      await authService.logout();
    } catch (err) {
      console.error("Account deletion failed:", err);
      setError("We couldn't delete your account. Please try again, or contact support.");
      setDeleting(false);
    }
  };

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Delete your account?</DialogTitle>
        <DialogDescription>
          Your agents, conversations, knowledge bases, automations and connections are deleted, and you are
          signed out everywhere. This can't be undone.
        </DialogDescription>
      </DialogHeader>
      <div className={styles.deleteAccountField}>
        <Label htmlFor="delete-account-email">Type {email} to confirm</Label>
        <Input
          id="delete-account-email"
          type="email"
          autoComplete="off"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          disabled={deleting}
        />
      </div>
      {error && <AlertBanner variant="error" message={error} />}
      <DialogFooter>
        <Button variant="outline" onClick={onCancel} disabled={deleting}>
          Cancel
        </Button>
        <Button variant="destructive" onClick={deleteAccount} disabled={!confirmed || deleting}>
          {deleting ? "Deleting..." : "Delete account"}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
