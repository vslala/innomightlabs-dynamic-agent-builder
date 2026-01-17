import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { SchemaForm } from "../../components/forms";
import { agentApiService } from "../../services/agents/AgentApiService";
import type { FormSchema } from "../../types/form";

export function AgentCreate() {
  const navigate = useNavigate();
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const loadSchema = async () => {
      try {
        const formSchema = await agentApiService.getCreateSchema();
        setSchema(formSchema);
      } catch (err) {
        setError("Failed to load form. Please try again.");
        console.error("Error loading schema:", err);
      } finally {
        setLoading(false);
      }
    };

    loadSchema();
  }, []);

  const handleSubmit = async (data: Record<string, string>) => {
    setIsSubmitting(true);
    setError(null);
    try {
      await agentApiService.createAgent(data);
      navigate("/dashboard/agents");
    } catch (err) {
      setError("Failed to create agent. Please try again.");
      console.error("Error creating agent:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    navigate("/dashboard/agents");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (error && !schema) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <p className="text-red-400">{error}</p>
        <Button onClick={() => window.location.reload()}>Try Again</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate("/dashboard/agents")}
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h2 className="text-xl font-semibold text-[var(--text-primary)]">
            Create New Agent
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            Configure your AI agent's identity and capabilities
          </p>
        </div>
      </div>

      {/* Form Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Agent Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}
          {schema && (
            <SchemaForm
              schema={schema}
              onSubmit={handleSubmit}
              onCancel={handleCancel}
              submitLabel="Create Agent"
              isLoading={isSubmitting}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
