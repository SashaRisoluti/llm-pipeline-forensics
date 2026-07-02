# Project: Failure Forensics Tool for AI Pipelines

### What You're Building

An observability layer for multi-step AI pipelines that traces every intermediate step, identifies exactly where failures originate, and feeds flagged failures into a growing evaluation dataset.

### Why It Lands Interviews

When a multi-step AI pipeline produces garbage, most teams have no idea which step broke. You're building the tool that answers **"Where did this go wrong?"** Being able to articulate why observability matters for AI systems is a senior-level signal.

## Tech Stack

| Component          | Tool                         |
| ------------------ | ---------------------------- |
| Pipeline Framework | Custom chain or LangChain    |
| Tracing            | OpenTelemetry + custom spans |
| Storage            | SQLite + JSON trace files    |
| Visualization      | React or Streamlit           |
| Containerization   | Docker                       |

---

# Build Phases

### Phase 1: Build the Pipeline (Days 1–3)

Four steps:

* Intake (raw document)
* Extraction (LLM pulls structured entities)
* Classification (document type)
* Summarization (tailored to document type)

Each step is an isolated function with **Pydantic** typed inputs and outputs.

Inject realistic failure modes:

* missing dates
* ambiguous categories
* currency mismatches

---

### Phase 2: Build the Tracing Layer (Days 3–6)

Every execution gets a unique trace ID containing one **Span** per step.

Each span captures:

* input
* output
* LLM prompt
* raw response
* token count
* latency
* errors
* a confidence score (1–5) the model assigns its own output

Store traces as JSON files indexed in SQLite.

---

### Phase 3: Root Cause Analysis (Days 6–9)

Walk backward through spans on any flagged trace.

Use an **LLM-as-judge** to score each step's output quality given its input.

The first step with a significant quality drop is the root cause.

Categorize failures:

* Extraction Hallucination
* Misclassification
* Propagation Error
* Prompt Failure
* Context Loss

Produce a structured evidence chain explaining exactly what broke and how it propagated.

---

### Phase 4: Visual Trace Explorer (Days 9–11)

Pipeline visualized as nodes, color-coded by health:

* green (healthy)
* yellow (low confidence)
* red (root cause)

Clicking a node shows full span details.

Diff view shows what the step received vs. produced vs. should have produced.

One-click flagging runs the backward analysis and displays the diagnosis.

---

### Phase 5: Feedback Loop (Days 11–13)

Every confirmed flag auto-generates an eval case:

* original input
* failing step
* bad output
* corrected output
* failure category

Periodically re-run the full eval dataset to track whether known failures are resolved.

Dashboard shows:

* most common failure types
* which step fails most
* failure rate over time

---

### Phase 6: Polish (Days 13–14)

Process 50 documents, ensure 8–10 failures of different types.

Demo:

* bad output in
* trace explorer open
* root cause diagnosed in seconds

Lead with the framing:

> **"Reduces mean time to root cause for AI pipeline failures from hours of manual debugging to seconds of automated diagnosis."**
