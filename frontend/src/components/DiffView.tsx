import type { Diagnosis, SpanRecord } from "../api";

export default function DiffView({
  span, diagnosis, correctedOutput,
}: {
  span: SpanRecord;
  diagnosis: Diagnosis | null;
  correctedOutput: unknown | null;
}) {
  const judgement = diagnosis?.judgements.find((j) => j.step === span.step);
  return (
    <div>
      <h3>Received vs produced vs expected — {span.step}</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        <div><h4>Received (input)</h4><pre>{JSON.stringify(span.input, null, 2)}</pre></div>
        <div><h4>Produced (output)</h4><pre>{JSON.stringify(span.output, null, 2)}</pre></div>
        <div>
          <h4>Should have produced</h4>
          {correctedOutput != null
            ? <pre>{JSON.stringify(correctedOutput, null, 2)}</pre>
            : <p style={{ fontSize: 13 }}>{judgement ? `Judge: ${judgement.reasoning}` : "Flag the trace to get a judgement."}</p>}
        </div>
      </div>
    </div>
  );
}
