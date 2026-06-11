"use client";

import * as React from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
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
import { api, type ProgramSummary, type ProgramType } from "@/lib/api";

export default function ProgramsPage() {
  const [programs, setPrograms] = React.useState<ProgramSummary[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [name, setName] = React.useState("");
  const [type, setType] = React.useState<ProgramType>("literature_synthesis");
  const [goal, setGoal] = React.useState("");
  const [budget, setBudget] = React.useState("15");
  const [root, setRoot] = React.useState("");
  const [creating, setCreating] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listPrograms();
      setPrograms(res.programs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await api.createProgram({
        name,
        type,
        goal,
        budget_usd: Number(budget),
        root_hypothesis: root.trim() ? root : null,
      });
      setName("");
      setGoal("");
      setRoot("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="grid gap-8 md:grid-cols-[360px_1fr]">
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>New program</CardTitle>
          <CardDescription>Imports a research.yaml-style spec via POST /programs.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={onCreate}>
            <div className="space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="transformer-efficiency-survey"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="type">Type</Label>
              <select
                id="type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={type}
                onChange={(e) => setType(e.target.value as ProgramType)}
              >
                <option value="literature_synthesis">literature_synthesis</option>
                <option value="ml_experiment">ml_experiment</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="goal">Goal</Label>
              <Textarea
                id="goal"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Synthesize the strongest evidence on…"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="budget">Budget (USD)</Label>
              <Input
                id="budget"
                type="number"
                min="0.01"
                step="0.01"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="root">Root hypothesis (optional)</Label>
              <Textarea
                id="root"
                value={root}
                onChange={(e) => setRoot(e.target.value)}
                placeholder="A claim/direction to seed the DAG…"
              />
            </div>
            <Button type="submit" disabled={creating} className="w-full">
              {creating ? "Creating…" : "Create program"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">Programs</h1>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            Refresh
          </Button>
        </div>
        {error ? (
          <pre className="overflow-x-auto rounded-md border border-destructive bg-destructive/10 p-3 text-xs text-destructive">
            {error}
          </pre>
        ) : null}
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : programs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No programs yet. Create one, or run{" "}
            <code>pnpm crucible import examples/lit-synthesis/research.yaml</code>.
          </p>
        ) : (
          <div className="grid gap-3">
            {programs.map((program) => (
              <Link key={program.id} href={`/programs/${program.id}`}>
                <Card className="transition-colors hover:border-ring">
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="font-medium">{program.name}</p>
                      <p className="text-xs text-muted-foreground">{program.id}</p>
                    </div>
                    <Badge variant="secondary">{program.type}</Badge>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
