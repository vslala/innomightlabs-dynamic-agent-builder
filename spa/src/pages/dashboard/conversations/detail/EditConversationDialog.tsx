import { useState } from "react";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { Textarea } from "../../../../components/ui/textarea";
import { Label } from "../../../../components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../../../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../../components/ui/select";
import type { AgentResponse } from "../../../../services/agents/AgentApiService";
import type { ConversationResponse } from "../../../../types/conversation";
import styles from "./ConversationDialogs.module.css";

export interface ConversationEdits {
  title: string;
  description?: string;
  agent_id: string;
}

interface EditConversationDialogProps {
  conversation: ConversationResponse;
  agents: AgentResponse[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Saves the edits; a rejection keeps the dialog open with the error. */
  onSave: (edits: ConversationEdits) => Promise<void>;
}

export function EditConversationDialog({ open, onOpenChange, ...props }: EditConversationDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Mounted only while open, so each opening starts from the conversation as it is now */}
      {open && <EditConversationForm onClose={() => onOpenChange(false)} {...props} />}
    </Dialog>
  );
}

function EditConversationForm({
  conversation,
  agents,
  onSave,
  onClose,
}: Omit<EditConversationDialogProps, "open" | "onOpenChange"> & { onClose: () => void }) {
  const [title, setTitle] = useState(conversation.title);
  const [description, setDescription] = useState(conversation.description || "");
  const [agentId, setAgentId] = useState(conversation.agent_id);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!title.trim() || !agentId) return;
    setSaving(true);
    setError(null);
    try {
      await onSave({ title: title.trim(), description: description.trim() || undefined, agent_id: agentId });
      onClose();
    } catch (err) {
      console.error("Error updating conversation:", err);
      setError("Failed to update conversation. Please try again.");
      setSaving(false);
    }
  };

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Edit Conversation</DialogTitle>
        <DialogDescription>Update the conversation title, description, or assigned agent.</DialogDescription>
      </DialogHeader>
      <div className={styles.fields}>
        <div className={styles.field}>
          <Label htmlFor="conversation-title">Title *</Label>
          <Input id="conversation-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>

        <div className={styles.field}>
          <Label htmlFor="conversation-description">Description</Label>
          <Textarea
            id="conversation-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
          />
        </div>

        <div className={styles.field}>
          <Label htmlFor="conversation-agent">Agent *</Label>
          <Select value={agentId} onValueChange={setAgentId}>
            <SelectTrigger id="conversation-agent">
              <SelectValue placeholder="Select an agent" />
            </SelectTrigger>
            <SelectContent>
              {agents.map((agent) => (
                <SelectItem key={agent.agent_id} value={agent.agent_id}>
                  {agent.agent_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {error && <p className={styles.error} role="alert">{error}</p>}
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={save} disabled={!title.trim() || !agentId || saving}>
          {saving ? "Saving..." : "Save Changes"}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
