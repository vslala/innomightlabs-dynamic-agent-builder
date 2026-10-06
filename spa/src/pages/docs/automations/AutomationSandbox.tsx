/**
 * A live, throwaway copy of the automation workspace for the docs.
 *
 * It mounts the same `AutomationWorkspace` the dashboard uses, backed by
 * `useSandboxAutomation`, so the tutorial always shows the current editor.
 */

import { useState } from "react";
import { RotateCcw } from "lucide-react";

import { AutomationWorkspace } from "../../dashboard/automations/AutomationWorkspace";
import type { TutorialStage } from "./tutorialFixtures";
import { useSandboxAutomation } from "./useSandboxAutomation";
import styles from "./AutomationSandbox.module.css";

export function AutomationSandbox({
  stage,
  expand = null,
  caption,
}: {
  stage: TutorialStage;
  /** Node id of the card to open first; `start` opens the WHEN card. */
  expand?: string | null;
  caption: string;
}) {
  // Remounting is the reset: every piece of sandbox state starts over.
  const [generation, setGeneration] = useState(0);

  return (
    <figure className={styles.sandbox}>
      <div className={styles.toolbar}>
        <span className={styles.badge}>Live example</span>
        <span className={styles.note}>Click around. Nothing here is saved or sent.</span>
        <button type="button" className={styles.reset} onClick={() => setGeneration((value) => value + 1)}>
          <RotateCcw size={14} />
          Reset
        </button>
      </div>
      <div className={styles.frame} data-docs-embed>
        <SandboxWorkspace key={generation} stage={stage} expand={expand} />
      </div>
      <figcaption className={styles.caption}>{caption}</figcaption>
    </figure>
  );
}

function SandboxWorkspace({ stage, expand }: { stage: TutorialStage; expand: string | null }) {
  const sandbox = useSandboxAutomation(stage, expand);
  return (
    <AutomationWorkspace
      automation={sandbox.graph.automation}
      draft={sandbox.draft}
      runs={sandbox.runs}
      params={sandbox.params}
      gateway={sandbox.gateway}
      operations={sandbox.operations}
    />
  );
}
