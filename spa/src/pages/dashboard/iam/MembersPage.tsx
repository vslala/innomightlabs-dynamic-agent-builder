import * as React from "react";
import { MembersPanel, type MembersState } from "./MembersPanel";
import { loadMembers } from "./loadMembers";

export function MembersPage() {
  const [state, setState] = React.useState<MembersState>({ status: "loading" });
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    const controller = new AbortController();
    loadMembers(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ status: "loaded", ...data });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Please try again.",
          });
        }
      },
    );
    return () => controller.abort();
  }, [attempt]);

  function retry() {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }

  return <MembersPanel state={state} onRetry={retry} />;
}
