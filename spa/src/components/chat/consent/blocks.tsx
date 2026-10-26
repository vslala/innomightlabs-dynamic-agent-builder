import type { ComponentType } from "react";
import { AlertTriangle, Check, X } from "lucide-react";

import { Checkbox, Input, MarkdownRenderer, Textarea } from "../../ui";
import type { ConsentBlock, ConsentBlockKind } from "../../../types/consent";
import styles from "./ConsentCard.module.css";

type BlockOf<K extends ConsentBlockKind> = Extract<ConsentBlock, { kind: K }>;

/** The person's draft of the editable arguments, while they edit before approving. */
export interface BlockEdit {
  editable: ReadonlySet<string>;
  draft: Record<string, unknown>;
  onChange: (argument: string, value: unknown) => void;
}

export interface BlockProps<K extends ConsentBlockKind> {
  block: BlockOf<K>;
  /** Set while editing: a block edits in place only the arguments it shows. */
  edit?: BlockEdit;
}

function editing(edit: BlockEdit | undefined, argument: string | null | undefined): edit is BlockEdit {
  return Boolean(edit && argument && edit.editable.has(argument));
}

function TextBlockView({ block, edit }: BlockProps<"text">) {
  return (
    <div className={styles.block}>
      {block.label && <div className={styles.label}>{block.label}</div>}
      {editing(edit, block.argument) ? (
        <Textarea
          aria-label={block.label ?? "Text"}
          rows={Math.min(12, Math.max(3, block.value.split("\n").length + 1))}
          value={String(edit.draft[block.argument!] ?? block.value)}
          onChange={(event) => edit.onChange(block.argument!, event.target.value)}
        />
      ) : block.format === "markdown" ? (
        <MarkdownRenderer content={block.value} />
      ) : (
        <p className={styles.text}>{block.value}</p>
      )}
    </div>
  );
}

function EmailBlockView({ block, edit }: BlockProps<"email">) {
  const subjectArgument = block.arguments.subject;
  const bodyArgument = block.arguments.body;
  const recipients: [string, string[]][] = [["To", block.to], ["Cc", block.cc], ["Bcc", block.bcc]];
  return (
    <div className={styles.block}>
      <dl className={styles.email}>
        {recipients
          .filter(([, mailboxes]) => mailboxes.length > 0)
          .map(([label, mailboxes]) => (
            <div key={label} className={styles.emailRow}>
              <dt>{label}</dt>
              <dd>{mailboxes.join(", ")}</dd>
            </div>
          ))}
        <div className={styles.emailRow}>
          <dt>Subject</dt>
          <dd>
            {editing(edit, subjectArgument) ? (
              <Input
                aria-label="Subject"
                value={String(edit.draft[subjectArgument!] ?? block.subject)}
                onChange={(event) => edit.onChange(subjectArgument!, event.target.value)}
              />
            ) : (
              block.subject || "(no subject)"
            )}
          </dd>
        </div>
      </dl>
      {editing(edit, bodyArgument) ? (
        <Textarea
          aria-label="Body"
          rows={8}
          value={String(edit.draft[bodyArgument!] ?? block.body)}
          onChange={(event) => edit.onChange(bodyArgument!, event.target.value)}
        />
      ) : block.html_body ? (
        // Never inline: the HTML comes from the model, so it renders in a frame that can't script or reach the page
        <iframe className={styles.htmlBody} title="Email body" sandbox="" srcDoc={block.html_body} />
      ) : (
        <p className={styles.text}>{block.body}</p>
      )}
    </div>
  );
}

function ImagesBlockView({ block }: BlockProps<"images">) {
  return (
    <div className={styles.block}>
      {block.label && <div className={styles.label}>{block.label}</div>}
      <div className={styles.images}>
        {block.items.map((image) => (
          <img key={image.url} src={image.url} alt={image.alt_text ?? ""} className={styles.image} />
        ))}
      </div>
    </div>
  );
}

function TargetsBlockView({ block }: BlockProps<"targets">) {
  return (
    <div className={styles.block}>
      <div className={styles.label}>{block.label}</div>
      <ul className={styles.targets}>
        {block.items.map((target) => (
          <li key={target.label} className={target.will_run ? styles.targetGoes : styles.targetSkipped}>
            {target.will_run ? <Check className="h-4 w-4" aria-hidden /> : <X className="h-4 w-4" aria-hidden />}
            <span>
              {target.label}
              {!target.will_run && <span className={styles.muted}> · skipped{target.reason ? `: ${target.reason}` : ""}</span>}
              {target.detail && <span className={styles.muted}> · {target.detail}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FieldsBlockView({ block, edit }: BlockProps<"fields">) {
  return (
    <div className={styles.block}>
      {block.label && <div className={styles.label}>{block.label}</div>}
      <dl className={styles.fields}>
        {block.items.map((field) => (
          <div key={field.label} className={styles.field}>
            <dt>{field.label}</dt>
            <dd>
              {editing(edit, field.argument) ? (
                <Input
                  aria-label={field.label}
                  value={String(edit.draft[field.argument!] ?? field.value)}
                  onChange={(event) => edit.onChange(field.argument!, event.target.value)}
                />
              ) : (
                field.value
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function GrantsBlockView({ block, edit }: BlockProps<"grants">) {
  const ticked = editing(edit, block.argument)
    ? new Set((edit.draft[block.argument] as string[] | undefined) ?? block.items.filter((item) => item.checked).map((item) => item.key))
    : new Set(block.items.filter((item) => item.checked).map((item) => item.key));
  const toggle = (key: string) => {
    if (!editing(edit, block.argument)) return;
    const next = new Set(ticked);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    edit.onChange(block.argument, [...next]);
  };
  return (
    <div className={styles.block}>
      <div className={styles.label}>{block.label}</div>
      <ul className={styles.grants}>
        {block.items.map((item) => (
          <li key={item.key}>
            <label className={styles.grant}>
              <Checkbox
                checked={item.always_allowed || ticked.has(item.key)}
                disabled={item.always_allowed || !editing(edit, block.argument)}
                onChange={() => toggle(item.key)}
              />
              <span>
                {item.title}
                {item.always_allowed && <span className={styles.muted}> · always allowed for this agent</span>}
                {item.warning && <span className={styles.muted}> · {item.warning}</span>}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CodeBlockView({ block }: BlockProps<"code">) {
  return (
    <details className={styles.block}>
      <summary className={styles.label}>{block.label ?? "Details"}</summary>
      <pre className={styles.code}>{block.value}</pre>
    </details>
  );
}

function WarningBlockView({ block }: BlockProps<"warning">) {
  return (
    <p className={styles.warning}>
      <AlertTriangle className="h-4 w-4" aria-hidden />
      {block.text}
    </p>
  );
}

/** One renderer per block kind; a kind the API adds doesn't compile here until it has one. */
const BLOCK_RENDERERS: { [K in ConsentBlockKind]: ComponentType<BlockProps<K>> } = {
  text: TextBlockView,
  email: EmailBlockView,
  images: ImagesBlockView,
  targets: TargetsBlockView,
  fields: FieldsBlockView,
  grants: GrantsBlockView,
  code: CodeBlockView,
  warning: WarningBlockView,
};

export function ConsentBlockView({ block, edit }: { block: ConsentBlock; edit?: BlockEdit }) {
  const Renderer = BLOCK_RENDERERS[block.kind] as ComponentType<{ block: ConsentBlock; edit?: BlockEdit }>;
  return <Renderer block={block} edit={edit} />;
}
