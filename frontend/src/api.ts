export interface SpanRecord {
  span_id: string;
  trace_id: string;
  step: string;
  status: "ok" | "error";
  latency_ms: number;
  started_at: string;
  error: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  confidence: number | null;
  input: unknown;
  output: unknown;
  prompt: string | null;
  raw_response: string | null;
}

export interface TraceDoc {
  trace_id: string;
  doc_id: string | null;
  created_at: string;
  status: string;
  spans: SpanRecord[];
}

export interface TraceSummary {
  trace_id: string;
  doc_id: string | null;
  created_at: string;
  status: string;
  flagged: number;
  root_cause_step: string | null;
  category: string | null;
}

export interface Judgement {
  step: string;
  score: number;
  reasoning: string;
}

export interface Diagnosis {
  trace_id: string;
  root_cause_step: string;
  category: string;
  confident: boolean;
  judgements: Judgement[];
  evidence_chain: string[];
}

export interface EvalCaseSummary {
  case_id: string;
  trace_id: string;
  failing_step: string;
  category: string;
  created_at: string;
}

export interface Stats {
  failure_types: { category: string; count: number }[];
  failures_per_step: { step: string; count: number }[];
  rate_over_time: { day: string; total: number; flagged: number }[];
  eval_trend: { run_at: string; total: number; passed: number }[];
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export const api = {
  listTraces: () => get<TraceSummary[]>("/api/traces"),
  getTrace: (id: string) => get<TraceDoc>(`/api/traces/${id}`),
  flagTrace: (id: string) => post<Diagnosis>(`/api/traces/${id}/flag`),
  getDiagnosis: (id: string) => get<Diagnosis>(`/api/traces/${id}/diagnosis`),
  createEval: (traceId: string, corrected: unknown) =>
    post<EvalCaseSummary>("/api/evals", { trace_id: traceId, corrected_output: corrected }),
  listEvals: (traceId?: string) =>
    get<EvalCaseSummary[]>(traceId ? `/api/evals?trace_id=${traceId}` : "/api/evals"),
  runEvals: () => post<{ case_id: string; passed: boolean; score: number }[]>("/api/evals/run"),
  stats: () => get<Stats>("/api/stats"),
};
