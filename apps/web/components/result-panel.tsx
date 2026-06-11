"use client";

import { Badge } from "@/components/ui/badge";

export function ResultPanel({
  data,
  error,
  loading,
}: {
  data?: unknown;
  error?: string | null;
  loading?: boolean;
}) {
  if (loading) {
    return <p className="text-sm text-muted-foreground">Running…</p>;
  }
  if (error) {
    return (
      <pre className="overflow-x-auto rounded-md border border-destructive bg-destructive/10 p-3 text-xs text-destructive">
        {error}
      </pre>
    );
  }
  if (data === undefined) {
    return <p className="text-sm text-muted-foreground">No result yet.</p>;
  }

  const degraded =
    data !== null && typeof data === "object" && (data as Record<string, unknown>).degraded === true;

  return (
    <div className="space-y-2">
      {degraded ? <Badge variant="warning">degraded</Badge> : null}
      <pre className="max-h-96 overflow-auto rounded-md border bg-muted/40 p-3 text-xs">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
