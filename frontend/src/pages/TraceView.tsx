import { ReactFlow, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Diagnosis, type TraceDoc } from "../api";
import DiagnosisPanel from "../components/DiagnosisPanel";
import DiffView from "../components/DiffView";
import SpanDrawer from "../components/SpanDrawer";
import { traceToFlow } from "../traceFlow";

export default function TraceView() {
  const { traceId } = useParams<{ traceId: string }>();
  const [trace, setTrace] = useState<TraceDoc | null>(null);
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [correctedOutput, setCorrectedOutput] = useState<unknown | null>(null);
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [flagging, setFlagging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!traceId) return;
    api.getTrace(traceId).then(setTrace).catch((e) => setError(String(e)));
    api.getDiagnosis(traceId).then(setDiagnosis).catch(() => setDiagnosis(null));
  }, [traceId]);

  const flow = useMemo(
    () => (trace ? traceToFlow(trace.spans, diagnosis) : { nodes: [], edges: [] }),
    [trace, diagnosis],
  );

  async function flag() {
    if (!traceId) return;
    setFlagging(true);
    try {
      setDiagnosis(await api.flagTrace(traceId));
    } catch (e) {
      setError(String(e));
    } finally {
      setFlagging(false);
    }
  }

  if (error) return <p>{error}</p>;
  if (!trace) return <p>Loading…</p>;

  const selectedSpan = trace.spans.find((s) => s.step === selectedStep);
  const rootSpan = diagnosis
    ? trace.spans.find((s) => s.step === diagnosis.root_cause_step)
    : undefined;

  return (
    <>
      <h2>
        Trace {trace.trace_id.slice(0, 12)}… — {trace.doc_id ?? "?"}{" "}
        <button onClick={flag} disabled={flagging}>
          {flagging ? "Diagnosing…" : diagnosis ? "Re-run diagnosis" : "Flag: find root cause"}
        </button>
      </h2>
      <div style={{ height: 260, border: "1px solid #2a2e39", borderRadius: 8 }}>
        <ReactFlow
          nodes={flow.nodes}
          edges={flow.edges}
          onNodeClick={(_evt, node: Node) => setSelectedStep(node.id)}
          fitView
          colorMode="dark"
        />
      </div>
      {diagnosis && (
        <DiagnosisPanel
          diagnosis={diagnosis}
          rootSpan={rootSpan}
          onEvalCreated={setCorrectedOutput}
        />
      )}
      {selectedSpan && (
        <>
          <SpanDrawer span={selectedSpan} />
          <DiffView
            span={selectedSpan}
            diagnosis={diagnosis}
            correctedOutput={
              diagnosis && selectedSpan.step === diagnosis.root_cause_step
                ? correctedOutput
                : null
            }
          />
        </>
      )}
    </>
  );
}
