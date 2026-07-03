import { useState } from "react";
import { api, type Diagnosis, type SpanRecord } from "../api";

export default function DiagnosisPanel({
  diagnosis, rootSpan, onEvalCreated,
}: {
  diagnosis: Diagnosis;
  rootSpan: SpanRecord | undefined;
  onEvalCreated: (corrected: unknown) => void;
}) {
  const [corrected, setCorrected] = useState(
    JSON.stringify(rootSpan?.output ?? {}, null, 2),
  );
  const [status, setStatus] = useState<string | null>(null);

  async function confirmFlag() {
    try {
      const parsed = JSON.parse(corrected);
      await api.createEval(diagnosis.trace_id, parsed);
      setStatus("Eval case created.");
      onEvalCreated(parsed);
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <div style={{ border: "1px solid #e5484d", borderRadius: 8, padding: 16, marginTop: 16 }}>
      <h3>
        Diagnosis: root cause = <strong>{diagnosis.root_cause_step}</strong>{" "}
        ({diagnosis.category}){!diagnosis.confident && " — low confidence"}
      </h3>
      <ol>
        {diagnosis.evidence_chain.map((line, i) => <li key={i}>{line}</li>)}
      </ol>
      <h4>Corrected output (edit, then confirm to create an eval case)</h4>
      <textarea rows={8} value={corrected} onChange={(e) => setCorrected(e.target.value)} />
      <p>
        <button onClick={confirmFlag}>Confirm flag → create eval case</button>{" "}
        {status && <small>{status}</small>}
      </p>
    </div>
  );
}
