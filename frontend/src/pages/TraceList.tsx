import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type TraceSummary } from "../api";

export default function TraceList() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listTraces().then(setTraces).catch((e) => setError(String(e)));
  }, []);

  if (error) return <p>Failed to load traces: {error}</p>;
  return (
    <>
      <h2>Traces</h2>
      <table>
        <thead>
          <tr><th>Trace</th><th>Document</th><th>Created</th><th>Status</th><th>Root cause</th><th>Category</th></tr>
        </thead>
        <tbody>
          {traces.map((t) => (
            <tr key={t.trace_id}>
              <td><Link to={`/traces/${t.trace_id}`}>{t.trace_id.slice(0, 12)}…</Link></td>
              <td>{t.doc_id ?? "—"}</td>
              <td>{t.created_at.slice(0, 19)}</td>
              <td>
                <span className={`badge ${t.status}`}>{t.status}</span>{" "}
                {t.flagged === 1 && <span className="badge flagged">flagged</span>}
              </td>
              <td>{t.root_cause_step ?? "—"}</td>
              <td>{t.category ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
