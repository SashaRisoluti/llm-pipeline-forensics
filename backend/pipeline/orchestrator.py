from opentelemetry.trace import StatusCode

from pipeline.steps import classify, extract, intake, summarize


class PipelineHalted(Exception):
    """A step failed; downstream steps are skipped."""


def run_pipeline(text: str, doc_id: str, llm, tracer, recorder) -> str:
    """Run the 4-step chain under one trace. Returns the trace_id (hex)."""
    with tracer.start_as_current_span("pipeline") as root:
        trace_id = format(root.get_span_context().trace_id, "032x")
        recorder.record(root.get_span_context().span_id, input={"doc_id": doc_id})
        try:
            doc = _step(tracer, recorder, "intake",
                        inp={"doc_id": doc_id, "text": text},
                        fn=lambda: intake(text, doc_id))
            entities = _step(tracer, recorder, "extract",
                             inp=doc.model_dump(),
                             fn=lambda: extract(llm, doc))
            cls = _step(tracer, recorder, "classify",
                        inp={"doc": doc.model_dump(), "entities": entities.model_dump()},
                        fn=lambda: classify(llm, doc, entities))
            _step(tracer, recorder, "summarize",
                  inp={"doc": doc.model_dump(), "entities": entities.model_dump(),
                       "doc_type": cls.doc_type.value},
                  fn=lambda: summarize(llm, doc, entities, cls.doc_type))
        except PipelineHalted as halted:
            root.set_status(StatusCode.ERROR, str(halted))
    return trace_id


def _step(tracer, recorder, name: str, inp: dict, fn):
    with tracer.start_as_current_span(name) as span:
        span_id = span.get_span_context().span_id
        recorder.record(span_id, input=inp)
        try:
            output, call = fn()
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            recorder.record(span_id, error=str(exc))
            raise PipelineHalted(f"{name}: {exc}") from exc
        payload = {"output": output.model_dump(mode="json")}
        if call is not None:
            payload.update(prompt=call.prompt, raw_response=call.raw_response,
                           tokens_in=call.tokens_in, tokens_out=call.tokens_out)
        if hasattr(output, "confidence"):
            payload["confidence"] = output.confidence
        recorder.record(span_id, **payload)
        return output
