// Browser client for the Crucible FastAPI control plane. The UI talks to FastAPI
// only — never to the MCP server, Neo4j, Redis, or Postgres directly.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type ProgramType = "literature_synthesis" | "ml_experiment";

export interface Budget {
  cap_usd: number | string;
  spent_usd: number | string;
}

export interface ProgramSummary {
  id: string;
  name: string;
  type: string;
  version: string;
  owner: string | null;
  created_at: string;
}

export interface Program extends ProgramSummary {
  updated_at: string;
  budget: Budget;
  root_hypothesis_id: string | null;
}

export interface DagNode {
  id: string;
  parent_id: string | null;
  depth: number;
  status: string;
  compact_summary: string;
}

export interface Dag {
  program_id: string;
  nodes: DagNode[];
  next_cursor: string | null;
}

export interface Hypothesis {
  id: string;
  program_id: string;
  parent_id: string | null;
  depth: number;
  status: string;
  compact_summary: string;
  proposal_hash: string;
  patch_diff_ref: string | null;
  proposer_run_id: string | null;
  neo4j_context_ref: string | null;
  trace_ref: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProgramSpecInput {
  name: string;
  type: ProgramType;
  goal: string;
  budget_usd: number;
  beam?: { min: number; max: number };
  backend?: string;
  metrics?: string[];
  sources?: string[];
  root_hypothesis?: string | null;
}

export interface GraphQueryInput {
  kind: "node_by_id" | "neighbors" | "claims_for_program";
  node_id?: string | null;
  program_id?: string | null;
  relationship?: string | null;
  limit?: number;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await res.text();
  if (!res.ok) {
    throw new ApiError(res.status, text || res.statusText);
  }
  return (text ? JSON.parse(text) : null) as T;
}

export const api = {
  // --- programs / DAG (Sprint 2) ---
  listPrograms: () => req<{ programs: ProgramSummary[] }>("/programs"),
  createProgram: (spec: ProgramSpecInput) =>
    req<Program>("/programs", { method: "POST", body: JSON.stringify(spec) }),
  getProgram: (id: string) => req<Program>(`/programs/${id}`),
  getDag: (id: string, cursor?: string | null) =>
    req<Dag>(`/programs/${id}/dag${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`),
  getHypothesis: (id: string) => req<Hypothesis>(`/hypotheses/${id}`),

  // --- tools (Sprint 3) ---
  toolDagNode: (id: string) => req<unknown>(`/tools/dag-node/${id}`),
  toolRunSummary: (id: string) => req<unknown>(`/tools/run-summary/${id}`),
  toolSearchClaims: (text: string, k = 10) =>
    req<unknown>(`/tools/search-claims?text=${encodeURIComponent(text)}&k=${k}`),
  toolQueryGraph: (body: GraphQueryInput) =>
    req<unknown>("/tools/query-domain-graph", { method: "POST", body: JSON.stringify(body) }),
  toolContextPack: (id: string) => req<unknown>(`/tools/context-pack/${id}`),
  toolRecordClaim: (body: { hypothesis_id: string; statement: string; proposed_confidence?: number }) =>
    req<unknown>("/tools/record-claim", { method: "POST", body: JSON.stringify(body) }),
};
