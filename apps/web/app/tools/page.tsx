"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ResultPanel } from "@/components/result-panel";
import { api, type GraphQueryInput } from "@/lib/api";

function useRunner() {
  const [data, setData] = React.useState<unknown>(undefined);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const run = React.useCallback(async (fn: () => Promise<unknown>) => {
    setLoading(true);
    setError(null);
    setData(undefined);
    try {
      setData(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  return { data, error, loading, run };
}

function ByIdTool({
  title,
  description,
  label,
  action,
}: {
  title: string;
  description: string;
  label: string;
  action: (id: string) => Promise<unknown>;
}) {
  const [id, setId] = React.useState("");
  const r = useRunner();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label>{label}</Label>
          <Input value={id} onChange={(e) => setId(e.target.value)} placeholder="uuid" />
        </div>
        <Button size="sm" disabled={!id} onClick={() => void r.run(() => action(id))}>
          Run
        </Button>
        <ResultPanel data={r.data} error={r.error} loading={r.loading} />
      </CardContent>
    </Card>
  );
}

function SearchClaimsTool() {
  const [text, setText] = React.useState("");
  const [k, setK] = React.useState("10");
  const r = useRunner();
  return (
    <Card>
      <CardHeader>
        <CardTitle>search_claims</CardTitle>
        <CardDescription>Lexical match now; semantic recall arrives in Sprint 6.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label>Text</Label>
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="quantization" />
        </div>
        <div className="space-y-1.5">
          <Label>k</Label>
          <Input type="number" min="1" max="50" value={k} onChange={(e) => setK(e.target.value)} />
        </div>
        <Button
          size="sm"
          disabled={!text}
          onClick={() => void r.run(() => api.toolSearchClaims(text, Number(k)))}
        >
          Run
        </Button>
        <ResultPanel data={r.data} error={r.error} loading={r.loading} />
      </CardContent>
    </Card>
  );
}

function GraphQueryTool() {
  const [kind, setKind] = React.useState<GraphQueryInput["kind"]>("node_by_id");
  const [nodeId, setNodeId] = React.useState("");
  const [programId, setProgramId] = React.useState("");
  const [relationship, setRelationship] = React.useState("");
  const r = useRunner();

  function submit() {
    const body: GraphQueryInput = {
      kind,
      node_id: nodeId || null,
      program_id: programId || null,
      relationship: relationship || null,
    };
    void r.run(() => api.toolQueryGraph(body));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>query_domain_graph</CardTitle>
        <CardDescription>Allow-listed, bounded-depth templates — no raw Cypher.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label>Kind</Label>
          <select
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={kind}
            onChange={(e) => setKind(e.target.value as GraphQueryInput["kind"])}
          >
            <option value="node_by_id">node_by_id</option>
            <option value="neighbors">neighbors</option>
            <option value="claims_for_program">claims_for_program</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>node_id</Label>
          <Input value={nodeId} onChange={(e) => setNodeId(e.target.value)} placeholder="graph node id" />
        </div>
        <div className="space-y-1.5">
          <Label>program_id</Label>
          <Input value={programId} onChange={(e) => setProgramId(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>relationship (neighbors only)</Label>
          <Input
            value={relationship}
            onChange={(e) => setRelationship(e.target.value)}
            placeholder="SUPPORTS | CONTRADICTS | USES | …"
          />
        </div>
        <Button size="sm" onClick={submit}>
          Run
        </Button>
        <ResultPanel data={r.data} error={r.error} loading={r.loading} />
      </CardContent>
    </Card>
  );
}

function RecordClaimTool() {
  const [hypothesisId, setHypothesisId] = React.useState("");
  const [statement, setStatement] = React.useState("");
  const r = useRunner();
  return (
    <Card>
      <CardHeader>
        <CardTitle>record_claim</CardTitle>
        <CardDescription>Staged write only — lands in crucible.claim_staging.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label>hypothesis_id</Label>
          <Input value={hypothesisId} onChange={(e) => setHypothesisId(e.target.value)} placeholder="uuid" />
        </div>
        <div className="space-y-1.5">
          <Label>statement</Label>
          <Textarea value={statement} onChange={(e) => setStatement(e.target.value)} />
        </div>
        <Button
          size="sm"
          disabled={!hypothesisId || !statement}
          onClick={() =>
            void r.run(() =>
              api.toolRecordClaim({ hypothesis_id: hypothesisId, statement }),
            )
          }
        >
          Stage claim
        </Button>
        <ResultPanel data={r.data} error={r.error} loading={r.loading} />
      </CardContent>
    </Card>
  );
}

export default function ToolsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">MCP tool playground</h1>
        <p className="text-sm text-muted-foreground">
          The same parameterized, read-mostly tools agents use — exercised over the REST mirror.
        </p>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <ByIdTool
          title="get_dag_node"
          description="Look up a hypothesis (DAG node) by id."
          label="hypothesis_id"
          action={(id) => api.toolDagNode(id)}
        />
        <ByIdTool
          title="get_context_pack"
          description="Compact context for a hypothesis; flags degraded if Neo4j is down."
          label="hypothesis_id"
          action={(id) => api.toolContextPack(id)}
        />
        <ByIdTool
          title="get_run_summary"
          description="Look up an experiment run summary by id."
          label="run_id"
          action={(id) => api.toolRunSummary(id)}
        />
        <SearchClaimsTool />
        <GraphQueryTool />
        <RecordClaimTool />
      </div>
    </div>
  );
}
