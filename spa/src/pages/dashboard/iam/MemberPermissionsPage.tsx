import * as React from "react";
import { useParams } from "react-router-dom";
import { iamService } from "../../../services/iam";
import { loadMemberPermissions } from "./loadMemberPermissions";
import { MemberPermissionsPanel, type MemberPermissionsState } from "./MemberPermissionsPanel";
import { runMutation, type MutationState } from "./runMutation";

export function MemberPermissionsPage() {
  const { userId = "" } = useParams();
  const [state, setState] = React.useState<MemberPermissionsState>({ status: "loading" });
  const [attempt, setAttempt] = React.useState(0);
  const [mutation, setMutation] = React.useState<MutationState>({ pending: false });
  const inFlight = React.useRef(false);
  const mounted = React.useRef(false);

  React.useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  React.useEffect(() => {
    const controller = new AbortController();
    loadMemberPermissions(userId, controller.signal).then(
      (data) => { if (!controller.signal.aborted) setState({ status: "loaded", ...data }); },
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ status: "error", message: error instanceof Error ? error.message : "Please try again." });
        }
      },
    );
    return () => controller.abort();
  }, [userId, attempt]);

  function mutate(operation: () => Promise<unknown>, message: string) {
    if (state.status !== "loaded" || !state.capabilities.can_manage_permissions) return;
    // Reloads after a failure too: another admin may have changed the member in between (409 CONFLICT)
    void runMutation(inFlight, operation, message,
      (result) => { if (mounted.current) setMutation(result); },
      () => { if (mounted.current) setAttempt((value) => value + 1); },
    );
  }

  return <MemberPermissionsPanel state={state} onRetry={() => setAttempt((value) => value + 1)} actions={{
    ...mutation,
    onAttach: (policy) => mutate(() => iamService.attachPolicy(userId, policy), "Policy attached."),
    onDetach: (policy) => mutate(() => iamService.detachPolicy(userId, policy), "Policy removed."),
  }} />;
}
