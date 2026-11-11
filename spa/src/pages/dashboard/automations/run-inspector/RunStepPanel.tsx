/**
 * One step of a run: its activity (every tool call, in order), what it produced, what it was given, and the
 * raw JSON of all three.
 */

import {
  JsonTreeViewer,
  MarkdownRenderer,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  CopyButton,
} from "../../../../components/ui";
import { stepReference } from "../chain/smartValues";
import { RunStatusBadge } from "../components/RunStatusBadge";
import { formatDuration } from "../components/runStatus";
import { ActivityTimeline } from "./ActivityTimeline";
import { ExpandableText, InspectorSection, ValueList } from "./parts";
import { hasActivity, stepKind, stepName, type InspectorTab, type RunStep } from "./runSteps";
import { asText } from "./toolCalls";
import { useStepToolCalls } from "./useStepToolCalls";

export function RunStepPanel({
  automationId,
  step,
  tab,
  selectedCallId,
  onTabChange,
  onSelectCall,
}: {
  automationId: string;
  step: RunStep;
  tab: InspectorTab;
  selectedCallId: string | null;
  onTabChange: (tab: InspectorTab) => void;
  onSelectCall: (callId: string | null) => void;
}) {
  const { result, node } = step;
  const toolCalls = useStepToolCalls(automationId, result);
  const reference = node ? stepReference(node) : null;
  const duration = formatDuration(result.started_at, result.completed_at);
  const failedCalls = toolCalls.calls.filter((call) => call.success === false).length;
  const prompt = typeof result.input.prompt === "string" ? result.input.prompt : null;
  const reply = replyText(result.output);

  return (
    <section className="run-inspector-step" aria-labelledby="run-inspector-step-title">
      <header className="run-inspector-step__head">
        <div className="run-inspector-step__title">
          <h2 id="run-inspector-step-title">{stepName(step)}</h2>
          <RunStatusBadge status={result.status} />
        </div>
        <div className="run-inspector-step__meta">
          {reference ? (
            <span className="run-inspector-ref">
              <code>{`{{ ${reference}.output }}`}</code>
              <CopyButton value={`{{ ${reference}.output }}`} label="Copy smart value reference" />
            </span>
          ) : null}
          <span>{stepKind(step)}</span>
          {duration ? <span>{duration}</span> : null}
        </div>
        {result.error ? (
          <div className="run-inspector-error" role="alert">
            <ExpandableText text={result.error} />
          </div>
        ) : null}
      </header>

      <Tabs value={tab} onValueChange={(value) => onTabChange(value as InspectorTab)}>
        <TabsList className="run-inspector-tabs" aria-label="Step data">
          {hasActivity(step) && (
            <TabsTrigger value="activity">
              Activity
              <span className="run-inspector-tabs__count">
                {result.tool_call_count}
                {failedCalls ? <span className="run-inspector-tabs__failed"> · {failedCalls} failed</span> : null}
              </span>
            </TabsTrigger>
          )}
          <TabsTrigger value="output">Output</TabsTrigger>
          <TabsTrigger value="input">Input</TabsTrigger>
          <TabsTrigger value="raw">Raw JSON</TabsTrigger>
        </TabsList>

        {hasActivity(step) && (
          <TabsContent value="activity" className="run-inspector-panel">
            <ActivityTimeline
              toolCalls={toolCalls}
              prompt={prompt}
              reply={reply}
              selectedCallId={selectedCallId}
              onSelectCall={onSelectCall}
              onShowInput={() => onTabChange("input")}
              onShowOutput={() => onTabChange("output")}
            />
          </TabsContent>
        )}

        <TabsContent value="output" className="run-inspector-panel">
          {reply !== null && (
            <InspectorSection title="Agent reply" actions={<CopyButton value={reply} label="Copy reply" />}>
              <MarkdownRenderer content={reply} className="run-inspector-reply" />
            </InspectorSection>
          )}
          <InspectorSection
            title={reference ? `Values later steps can use as ${reference}.output` : "Output"}
            actions={<CopyButton value={asText(result.output)} label="Copy output JSON" />}
          >
            <JsonTreeViewer value={result.output} maxHeight="none" />
          </InspectorSection>
        </TabsContent>

        <TabsContent value="input" className="run-inspector-panel">
          <StepInput input={result.input} prompt={prompt} />
        </TabsContent>

        <TabsContent value="raw" className="run-inspector-panel">
          <RawJson title="Input" value={result.input} />
          <RawJson title="Output" value={result.output} />
          {toolCalls.events.length > 0 && <RawJson title="Recorded tool events" value={toolCalls.events} />}
        </TabsContent>
      </Tabs>
    </section>
  );
}

function StepInput({ input, prompt }: { input: Record<string, unknown>; prompt: string | null }) {
  const rest = Object.fromEntries(Object.entries(input).filter(([key]) => key !== "prompt" || prompt === null));
  return (
    <>
      {prompt !== null && (
        <InspectorSection title="Prompt, with smart values filled in" actions={<CopyButton value={prompt} label="Copy prompt" />}>
          <ExpandableText text={prompt} />
        </InspectorSection>
      )}
      <InspectorSection title={prompt !== null ? "Other input" : "Input"}>
        <ValueList value={rest} empty="This step had no input." />
      </InspectorSection>
    </>
  );
}

function RawJson({ title, value }: { title: string; value: unknown }) {
  return (
    <InspectorSection title={title} actions={<CopyButton value={asText(value)} label={`Copy ${title.toLowerCase()} JSON`} />}>
      <JsonTreeViewer value={value} maxHeight="32rem" />
    </InspectorSection>
  );
}

/** The agent's answer: an agent step keeps it at `response_text`, an invoke-agent skill action under `result`. */
function replyText(output: Record<string, unknown>): string | null {
  const holder = typeof output.result === "object" && output.result !== null ? (output.result as Record<string, unknown>) : output;
  const text = output.response_text ?? holder.response_text;
  return typeof text === "string" ? text : null;
}
