import json
from typing import Any

from pydantic import BaseModel, Field

from pipeline.llm import LLMClient
from pipeline.models import Diagnosis, FailureCategory, StepJudgement

JUDGE_PROMPT = """You are a strict QA judge for the "{step}" step of a document pipeline.
Given the step's INPUT and its OUTPUT, score OUTPUT quality from 1 to 5:
5 = fully correct and faithful to the input;
3 = usable but with noticeable issues;
1 = wrong, fabricated, or contradicts the input.
Penalize invented facts (dates, amounts, parties not present in the input),
wrong classifications, and information lost from the input.
Explain your score in one or two sentences.

INPUT:
{input}

OUTPUT:
{output}
"""

CATEGORY_PROMPT = """A document pipeline failed. The diagnosed root-cause step is "{step}".
Per-step judge findings (in execution order):
{findings}

Pick the single best failure category:
- extraction_hallucination: extraction invented entities not present in the source
- misclassification: document type was classified wrongly
- propagation_error: an upstream mistake was inherited and amplified downstream
- context_loss: information present upstream was dropped, degrading the output
- prompt_failure: the step's prompt/LLM call itself failed or produced unusable output
Explain your choice in one sentence.
"""


class JudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    reasoning: str


class CategoryVerdict(BaseModel):
    category: FailureCategory
    explanation: str


def diagnose(trace_doc: dict[str, Any], llm: LLMClient) -> Diagnosis:
    spans = [s for s in trace_doc["spans"] if s["step"] != "pipeline"]
    judgements: list[StepJudgement] = []
    for s in spans:
        if s["status"] == "error":
            judgements.append(StepJudgement(
                step=s["step"], score=1,
                reasoning=f"step errored: {s.get('error')}"))
            continue
        prompt = JUDGE_PROMPT.format(
            step=s["step"],
            input=json.dumps(s.get("input"), default=str),
            output=json.dumps(s.get("output"), default=str),
        )
        try:
            verdict, _ = llm.generate_structured(prompt, JudgeVerdict)
            judgements.append(StepJudgement(
                step=s["step"], score=verdict.score, reasoning=verdict.reasoning))
        except Exception as exc:
            judgements.append(StepJudgement(
                step=s["step"], score=3, reasoning=f"unjudgeable: {exc}"))

    root_step, confident = _find_root_cause(judgements)
    category = _classify(llm, root_step, judgements)
    evidence = [f"{j.step}: score {j.score}/5 — {j.reasoning}" for j in judgements]
    return Diagnosis(
        trace_id=trace_doc["trace_id"], root_cause_step=root_step,
        category=category, confident=confident,
        judgements=judgements, evidence_chain=evidence,
    )


def _find_root_cause(judgements: list[StepJudgement]) -> tuple[str, bool]:
    prev_score = 5
    for j in judgements:
        if j.score <= prev_score - 2:
            return j.step, True
        prev_score = j.score
    worst = min(judgements, key=lambda j: j.score)
    return worst.step, False


def _classify(llm: LLMClient, root_step: str, judgements: list[StepJudgement]) -> FailureCategory:
    findings = "\n".join(f"- {j.step}: {j.score}/5 — {j.reasoning}" for j in judgements)
    prompt = CATEGORY_PROMPT.format(step=root_step, findings=findings)
    try:
        verdict, _ = llm.generate_structured(prompt, CategoryVerdict)
        return verdict.category
    except Exception:
        return FailureCategory.prompt_failure
