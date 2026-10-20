import { useState } from "react";
import { Loader2, Play } from "lucide-react";
import {
  AlertBanner,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../components/ui";
import { FieldGroup, Stack } from "../../../components/layout";
import { knowledgeApiService } from "../../../services/knowledge";
import type { CrawlJob, CrawlSourceType } from "../../../types/knowledge";
import styles from "./dialogs.module.css";

interface StartCrawlDialogProps {
  kbId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStarted: (job: CrawlJob) => void;
}

function messageOf(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "object" && err !== null) {
    const { detail, message } = err as Record<string, unknown>;
    if (typeof detail === "string") return detail;
    if (typeof message === "string") return message;
  }
  return "Failed to start crawl. Please try again.";
}

export function StartCrawlDialog({ kbId, open, onOpenChange, onStarted }: StartCrawlDialogProps) {
  const [sourceType, setSourceType] = useState<CrawlSourceType>("sitemap");
  const [sourceUrl, setSourceUrl] = useState("");
  const [maxPages, setMaxPages] = useState(100);
  const [maxDepth, setMaxDepth] = useState(3);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    if (!sourceUrl.trim()) return;
    setStarting(true);
    setError(null);
    try {
      const job = await knowledgeApiService.startCrawlJob(kbId, {
        source_type: sourceType,
        source_url: sourceUrl.trim(),
        max_pages: maxPages,
        max_depth: maxDepth,
      });
      setSourceUrl("");
      onStarted(job);
      onOpenChange(false);
    } catch (err: unknown) {
      console.error("Error starting crawl:", err);
      setError(messageOf(err));
    } finally {
      setStarting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setError(null);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start Web Crawl</DialogTitle>
          <DialogDescription>Crawl a website to import its content into this knowledge base.</DialogDescription>
        </DialogHeader>

        {error && <AlertBanner message={error} variant="error" />}

        <Stack gap="md" className={styles.fields}>
          <FieldGroup>
            <Label htmlFor="source-type">Source Type</Label>
            <Select value={sourceType} onValueChange={(value) => setSourceType(value as CrawlSourceType)}>
              <SelectTrigger id="source-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="sitemap">Sitemap URL</SelectItem>
                <SelectItem value="url">Starting URL</SelectItem>
              </SelectContent>
            </Select>
            <p className={styles.hint}>
              {sourceType === "sitemap"
                ? "Provide a sitemap.xml URL to crawl all listed pages"
                : "Provide a starting URL to crawl and follow links"}
            </p>
          </FieldGroup>

          <FieldGroup>
            <Label htmlFor="source-url">{sourceType === "sitemap" ? "Sitemap URL" : "Starting URL"}</Label>
            <Input
              id="source-url"
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder={sourceType === "sitemap" ? "https://example.com/sitemap.xml" : "https://example.com/docs"}
            />
          </FieldGroup>

          <div className={styles.numbers}>
            <FieldGroup>
              <Label htmlFor="max-pages">Max Pages</Label>
              <Input
                id="max-pages"
                type="number"
                min={1}
                max={1000}
                value={maxPages}
                onChange={(event) => setMaxPages(parseInt(event.target.value) || 100)}
              />
            </FieldGroup>
            <FieldGroup>
              <Label htmlFor="max-depth">Max Depth</Label>
              <Input
                id="max-depth"
                type="number"
                min={1}
                max={10}
                value={maxDepth}
                onChange={(event) => setMaxDepth(parseInt(event.target.value) || 3)}
              />
              <p className={styles.hint}>Only for URL crawling</p>
            </FieldGroup>
          </div>
        </Stack>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={starting}>
            Cancel
          </Button>
          <Button onClick={start} disabled={starting || !sourceUrl.trim()}>
            {starting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Starting...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Start Crawl
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
