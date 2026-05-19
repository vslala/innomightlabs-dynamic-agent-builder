import { BarChart3 } from "lucide-react";

import { Card, CardContent } from "../../../components/ui";

export function AutomationAnalyticsPage() {
  return (
    <Card>
      <CardContent className="p-12">
        <div className="text-center">
          <BarChart3 className="h-14 w-14 mx-auto text-[var(--text-muted)] mb-4" />
          <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
            Automation Analytics
          </h2>
          <p className="text-sm text-[var(--text-muted)]">
            Execution analytics will be added after the builder and run history workflow stabilizes.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
