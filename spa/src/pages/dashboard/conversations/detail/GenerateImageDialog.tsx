import { useState } from "react";
import { Button } from "../../../../components/ui/button";
import { Textarea } from "../../../../components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../../../components/ui/dialog";

interface GenerateImageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  generating: boolean;
  onGenerate: (prompt: string) => void;
}

export function GenerateImageDialog({ open, onOpenChange, generating, onGenerate }: GenerateImageDialogProps) {
  const [prompt, setPrompt] = useState("");

  const generate = () => {
    if (!prompt.trim() || generating) return;
    onGenerate(prompt.trim());
    setPrompt("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate Image</DialogTitle>
          <DialogDescription>Describe the image this agent should create.</DialogDescription>
        </DialogHeader>
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="A clean product hero image for..."
          aria-label="Image description"
          rows={5}
          disabled={generating}
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={generating}>
            Cancel
          </Button>
          <Button onClick={generate} disabled={!prompt.trim() || generating}>
            {generating ? "Generating..." : "Generate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
