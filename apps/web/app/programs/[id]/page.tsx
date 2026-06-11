"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ResultPanel } from "@/components/result-panel";
import { api, type Dag, type Hypothesis, type Program } from "@/lib/api";

function statusVariant(status: string): BadgeProps["variant"] {
  if (status === "kept") return "success";
  if (status === "rejected") return "destructive";
  if (status === "quarantined" || status === "escalated") return "warning";
  return "secondary";
}

export default function ProgramDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [program, setProgram] = React.useState<Program | null>(null);
  const [dag, setDag] = React.useState<Dag | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const [selected, setSelected] = React.useState<Hypothesis | null>(null);
  const [toolResult, setToolResult] = React.useState<unknown>(undefined);
  const [toolError, setToolError] = React.useState<string | null>(null);
  const [toolLoading, setToolLoading] = React.useState(false);

  React.useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [p, d] = await Promise.all([api.getProgram(id), api.getDag(id)]);
        if (!active) return;
        setProgram(p);
        setDag(d);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [id]);

  async function selectNode(nodeId: string) {
    setToolResult(undefined);
    setToolError(null);
    try {
      setSelected(await api.getHypothesis(nodeId));
    } catch (e) {
      setToolError(e instanceof Error ? e.message : String(e));
    }
  }

  async function runTool(fn: () => Promise<unknown>) {
    setToolLoading(true);
    setToolError(null);
    setToolResult(undefined);
    try {
      setToolResult(await fn());
    } catch (e) {
      setToolError(e instanceof Error ? e.message : String(e));
    } finally {
      setToolLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-muted-foreground hover:underline">
        ← Programs
      </Link>

      {error ? (
        <pre className="overflow-x-auto rounded-md border border-destructive bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </pre>
      ) : null}

      {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}

      {program ? (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
            <div>
              <h1 className="text-lg font-semibold">{program.name}</h1>
              <p className="text-xs text-muted-foreground">{program.id}</p>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Badge variant="secondary">{program.type}</Badge>
              <Badge variant="outline">
                budget ${String(program.budget.spent_usd)} / ${String(program.budget.cap_usd)}
              </Badge>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Hypothesis DAG</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {dag && dag.nodes.length > 0 ? (
              dag.nodes.map((node) => (
                <button
                  key={node.id}
                  onClick={() => void selectNode(node.id)}
                  className={`flex w-full items-start justify-between gap-3 rounded-md border p-3 text-left text-sm hover:border-ring ${
                    selected?.id === node.id ? "border-ring bg-accent/40" : ""
                  }`}
                  style={{ marginLeft: node.depth * 16 }}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {node.compact_summary || "(no summary)"}
                    </span>
                    <span className="text-xs text-muted-foreground">depth {node.depth}</span>
                  </span>
                  <Badge variant={statusVariant(node.status)}>{node.status}</Badge>
                </button>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No hypotheses yet.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Node detail &amp; tools</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {selected ? (
              <>
                <div className="space-y-1 text-sm">
                  <p className="font-medium">{selected.compact_summary || "(no summary)"}</p>
                  <p className="text-xs text-muted-foreground">id {selected.id}</p>
                  <p className="text-xs text-muted-foreground">
                    status {selected.status} · depth {selected.depth}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() => void runTool(() => api.toolContextPack(selected.id))}
                  >
                    get_context_pack
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void runTool(() => api.toolDagNode(selected.id))}
                  >
                    get_dag_node
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      void runTool(() =>
                        api.toolRecordClaim({
                          hypothesis_id: selected.id,
                          statement: "Staged claim from the test UI.",
                        }),
                      )
                    }
                  >
                    record_claim (staged)
                  </Button>
                </div>
                <ResultPanel data={toolResult} error={toolError} loading={toolLoading} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Select a hypothesis to inspect it.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
