import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, Copy, FileCheck2, Play } from "lucide-react";
import { SchemaForm } from "../../../components/forms";
import { Alert, AlertDescription, Button, Panel, PanelBody, PanelHeader, PanelTitle, StatusBadge, Textarea } from "../../../components/ui";
import {
  blueprintApiService,
  type BlueprintDeployment,
  type BlueprintDeploymentSummary,
  type BlueprintIssue,
  type BlueprintParams,
  type BlueprintPlan,
  type BlueprintValidation,
} from "../../../services/blueprints/BlueprintApiService";
import type { FormValue } from "../../../types/form";
import { DEPLOYMENT_STATUS, issueLocation, resourceLink, toParams } from "./blueprintView";
import styles from "./BlueprintsPage.module.css";

const FIRST_EXAMPLE = "site-agent";

function IssueList({ issues }: { issues: BlueprintIssue[] }) {
  return (
    <ul className={styles.issues}>
      {issues.map((issue, index) => (
        <li key={`${issue.path}-${index}`} className={styles.issue}>
          <AlertCircle className={styles.issueIcon} aria-hidden="true" />
          <div>
            <p className={styles.issueMessage}>{issue.message}</p>
            {issue.hint && <p className={styles.issueHint}>{issue.hint}</p>}
            <p className={styles.issueLocation}>{issueLocation(issue)}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function BlueprintsPage() {
  const [yaml, setYaml] = useState("");
  const [validation, setValidation] = useState<BlueprintValidation | null>(null);
  const [params, setParams] = useState<BlueprintParams>({});
  const [plan, setPlan] = useState<BlueprintPlan | null>(null);
  const [deployment, setDeployment] = useState<BlueprintDeployment | null>(null);
  const [deployments, setDeployments] = useState<BlueprintDeploymentSummary[]>([]);
  const [busy, setBusy] = useState<"validate" | "plan" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const loadDeployments = useCallback(async () => {
    try {
      setDeployments(await blueprintApiService.listDeployments());
    } catch (err) {
      console.error("Error loading deployments:", err);
    }
  }, []);

  useEffect(() => {
    blueprintApiService.getExample(FIRST_EXAMPLE).then(setYaml).catch((err) => {
      console.error("Error loading example blueprint:", err);
      setError("Couldn't load the example blueprint.");
    });
    loadDeployments();
  }, [loadDeployments]);

  const handleYamlChange = (value: string) => {
    setYaml(value);
    setValidation(null);
    setPlan(null);
    setDeployment(null);
  };

  const handleValidate = async () => {
    setBusy("validate");
    setError(null);
    setPlan(null);
    setDeployment(null);
    try {
      setValidation(await blueprintApiService.validate(yaml));
    } catch (err) {
      console.error("Error validating blueprint:", err);
      setError("Couldn't check the blueprint. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const handlePlan = async (values: Record<string, FormValue>) => {
    const nextParams = toParams(values);
    setParams(nextParams);
    setBusy("plan");
    setError(null);
    setDeployment(null);
    try {
      setPlan(await blueprintApiService.plan(yaml, nextParams));
    } catch (err) {
      console.error("Error planning blueprint:", err);
      setError("Couldn't plan the blueprint. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const handleApply = async () => {
    setBusy("apply");
    setError(null);
    try {
      setDeployment(await blueprintApiService.apply(yaml, params));
      setPlan(null);
      loadDeployments();
    } catch (err) {
      console.error("Error applying blueprint:", err);
      setError("Couldn't apply the blueprint. Your account may have changed since the plan; preview the plan again.");
    } finally {
      setBusy(null);
    }
  };

  const copy = async (name: string, value: string) => {
    await navigator.clipboard.writeText(value);
    setCopied(name);
    window.setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Blueprints</h2>
        <p className={styles.subtitle}>
          Describe a whole solution in one YAML file: knowledge bases, agents, skills and widget keys. Check it,
          preview what it will create, then apply it.
        </p>
      </header>

      {error && (
        <Alert variant="error">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className={styles.columns}>
        <Panel>
          <PanelHeader>
            <PanelTitle>Blueprint</PanelTitle>
          </PanelHeader>
          <PanelBody className={styles.editorBody}>
            <Textarea
              className={styles.editor}
              value={yaml}
              onChange={(event) => handleYamlChange(event.target.value)}
              spellCheck={false}
              aria-label="Blueprint YAML"
            />
            <div className={styles.actions}>
              <Button onClick={handleValidate} disabled={!yaml.trim() || busy !== null}>
                <FileCheck2 className={styles.buttonIcon} aria-hidden="true" />
                {busy === "validate" ? "Checking…" : "Check blueprint"}
              </Button>
            </div>
            {validation && !validation.valid && <IssueList issues={validation.issues} />}
          </PanelBody>
        </Panel>

        <div className={styles.side}>
          {validation?.valid && validation.params_form && (
            <Panel>
              <PanelHeader>
                <PanelTitle>{validation.params_form.form_name}</PanelTitle>
              </PanelHeader>
              <PanelBody>
                <SchemaForm
                  key={yaml}
                  schema={validation.params_form}
                  onSubmit={handlePlan}
                  submitLabel={busy === "plan" ? "Planning…" : "Preview plan"}
                  isLoading={busy === "plan"}
                />
              </PanelBody>
            </Panel>
          )}

          {plan && (
            <Panel>
              <PanelHeader>
                <PanelTitle>Plan</PanelTitle>
              </PanelHeader>
              <PanelBody className={styles.stack}>
                {plan.issues.length > 0 && <IssueList issues={plan.issues} />}
                {plan.steps.length > 0 && (
                  <ol className={styles.steps}>
                    {plan.steps.map((step) => (
                      <li key={step.resource} className={styles.step}>
                        <span className={styles.stepKind}>{step.kind}</span>
                        <span>{step.summary}</span>
                      </li>
                    ))}
                  </ol>
                )}
                {plan.blockers.length > 0 && (
                  <>
                    <p className={styles.blockedNote}>Fix these before applying:</p>
                    <IssueList issues={plan.blockers} />
                  </>
                )}
                {plan.ok && (
                  <Button onClick={handleApply} disabled={busy !== null}>
                    <Play className={styles.buttonIcon} aria-hidden="true" />
                    {busy === "apply" ? "Applying…" : "Apply"}
                  </Button>
                )}
              </PanelBody>
            </Panel>
          )}

          {deployment && (
            <Panel>
              <PanelHeader>
                <PanelTitle>{deployment.blueprint_title}</PanelTitle>
                <StatusBadge
                  status={DEPLOYMENT_STATUS[deployment.status].status}
                  label={DEPLOYMENT_STATUS[deployment.status].label}
                />
              </PanelHeader>
              <PanelBody className={styles.stack}>
                {deployment.error && (
                  <Alert variant="error">
                    <AlertDescription>{deployment.error}</AlertDescription>
                  </Alert>
                )}
                {Object.entries(deployment.outputs).map(([name, output]) => (
                  <div key={name} className={styles.output}>
                    <div className={styles.outputHeader}>
                      <span className={styles.outputName}>{name}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => copy(name, output.value)}
                        aria-label={`Copy ${name}`}
                      >
                        {copied === name ? <CheckCircle2 className={styles.buttonIcon} /> : <Copy className={styles.buttonIcon} />}
                      </Button>
                    </div>
                    {output.description && <p className={styles.outputDescription}>{output.description}</p>}
                    <code className={styles.outputValue}>{output.value}</code>
                  </div>
                ))}
                <ul className={styles.resources}>
                  {Object.entries(deployment.resources).map(([name, resource]) => {
                    const link = resourceLink(resource.kind, resource.id);
                    return (
                      <li key={name}>
                        <span className={styles.stepKind}>{resource.kind}</span>
                        {link ? <Link to={link}>{resource.attributes.name || name}</Link> : <span>{name}</span>}
                      </li>
                    );
                  })}
                </ul>
              </PanelBody>
            </Panel>
          )}
        </div>
      </div>

      {deployments.length > 0 && (
        <Panel>
          <PanelHeader>
            <PanelTitle>Past deployments</PanelTitle>
          </PanelHeader>
          <PanelBody>
            <ul className={styles.history}>
              {deployments.map((item) => (
                <li key={item.deployment_id} className={styles.historyRow}>
                  <span>{item.blueprint_title}</span>
                  <span className={styles.historyDate}>{new Date(item.created_at).toLocaleString()}</span>
                  <StatusBadge status={DEPLOYMENT_STATUS[item.status].status} label={DEPLOYMENT_STATUS[item.status].label} />
                </li>
              ))}
            </ul>
          </PanelBody>
        </Panel>
      )}
    </div>
  );
}
