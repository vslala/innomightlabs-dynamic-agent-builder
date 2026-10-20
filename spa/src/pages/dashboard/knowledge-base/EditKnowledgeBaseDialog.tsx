import { useEffect, useState } from "react";
import {
  AlertBanner,
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Textarea,
} from "../../../components/ui";
import { FieldGroup, Stack } from "../../../components/layout";
import { knowledgeApiService } from "../../../services/knowledge";
import type { KnowledgeBase } from "../../../types/knowledge";
import styles from "./dialogs.module.css";

interface EditKnowledgeBaseDialogProps {
  kb: KnowledgeBase;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (kb: KnowledgeBase) => void;
}

export function EditKnowledgeBaseDialog({ kb, open, onOpenChange, onSaved }: EditKnowledgeBaseDialogProps) {
  const [name, setName] = useState(kb.name);
  const [description, setDescription] = useState(kb.description || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Each time it opens it starts from what is saved
  useEffect(() => {
    if (open) {
      setName(kb.name);
      setDescription(kb.description || "");
      setError(null);
    }
  }, [open, kb]);

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await knowledgeApiService.updateKnowledgeBase(kb.kb_id, {
        name: name.trim(),
        description: description.trim() || undefined,
      });
      onSaved(updated);
      onOpenChange(false);
    } catch (err) {
      console.error("Error updating knowledge base:", err);
      setError("Failed to update knowledge base. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Knowledge Base</DialogTitle>
        </DialogHeader>
        {error && <AlertBanner message={error} variant="error" />}
        <Stack gap="md" className={styles.fields}>
          <FieldGroup>
            <Label htmlFor="kb-name">Name</Label>
            <Input id="kb-name" value={name} onChange={(event) => setName(event.target.value)} />
          </FieldGroup>
          <FieldGroup>
            <Label htmlFor="kb-description">Description</Label>
            <Textarea id="kb-description" value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
          </FieldGroup>
        </Stack>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={save} disabled={saving || !name.trim()}>
            {saving ? "Saving..." : "Save Changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
