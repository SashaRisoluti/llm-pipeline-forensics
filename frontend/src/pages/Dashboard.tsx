import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, type Stats } from "../api";

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid #2a2e39", borderRadius: 8, padding: 16 }}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      <div style={{ height: 240 }}>{children}</div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.stats().then(setStats).catch((e) => setError(String(e)));
  useEffect(() => { load(); }, []);

  async function runEvals() {
    setRunning(true);
    try {
      await api.runEvals();
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  if (error) return <p>{error}</p>;
  if (!stats) return <p>Loading…</p>;

  const evalTrend = stats.eval_trend.map((e) => ({
    ...e, resolved_pct: e.total ? Math.round((100 * e.passed) / e.total) : 0,
  }));

  return (
    <>
      <h2>
        Dashboard{" "}
        <button onClick={runEvals} disabled={running}>
          {running ? "Running evals…" : "Re-run eval dataset"}
        </button>
      </h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Panel title="Most common failure types">
          <ResponsiveContainer>
            <BarChart data={stats.failure_types}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e39" />
              <XAxis dataKey="category" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#e5484d" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Failures per step">
          <ResponsiveContainer>
            <BarChart data={stats.failures_per_step}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e39" />
              <XAxis dataKey="step" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#f5d90a" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Flagged traces over time">
          <ResponsiveContainer>
            <LineChart data={stats.rate_over_time}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e39" />
              <XAxis dataKey="day" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line dataKey="total" stroke="#7cb7ff" />
              <Line dataKey="flagged" stroke="#e5484d" />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Known failures resolved (% of eval cases passing)">
          <ResponsiveContainer>
            <LineChart data={evalTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e39" />
              <XAxis dataKey="run_at" tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} unit="%" />
              <Tooltip />
              <Line dataKey="resolved_pct" stroke="#30a46c" />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      </div>
    </>
  );
}
