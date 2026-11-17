import json
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evals.store import list_cases
from pipeline.llm import LLMClient
from pipeline.models import DocumentType, ExtractedEntities, RawDocument
from pipeline.steps import classify, extract, summarize

EVAL_JUDGE_PROMPT = """An earlier pipeline failure produced a corrected reference output.
Compare the NEW OUTPUT of the re-run step "{step}" against the CORRECTED OUTPUT.
Score 1-5: 5 = new output is as good as the correction (failure resolved);
1 = new output repeats the original failure. One-sentence reasoning.

STEP INPUT:
{input}

CORRECTED OUTPUT:
{corrected}

NEW OUTPUT:
{new}
"""


class EvalJudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    reasoning: str


def _rerun_step(llm: LLMClient, step: str, original_input: dict[str, Any]) -> BaseModel:
    out: BaseModel
    if step == "extract":
        out, _ = extract(llm, RawDocument(**original_input))
    elif step == "classify":
        out, _ = classify(llm, RawDocument(**original_input["doc"]),
                          ExtractedEntities(**original_input["entities"]))
    elif step == "summarize":
        out, _ = summarize(llm, RawDocument(**original_input["doc"]),
                           ExtractedEntities(**original_input["entities"]),
                           DocumentType(original_input["doc_type"]))
    else:
        raise ValueError(f"step {step} cannot be re-run")
    return out


def run_evals(
    conn: sqlite3.Connection, evals_dir: Path, llm: LLMClient, run_at: str
) -> list[dict[str, Any]]:
    results = []
    for case in list_cases(conn, evals_dir):
        try:
            new_output = _rerun_step(llm, case.failing_step, case.original_input)
            prompt = EVAL_JUDGE_PROMPT.format(
                step=case.failing_step,
                input=json.dumps(case.original_input, default=str),
                corrected=json.dumps(case.corrected_output, default=str),
                new=new_output.model_dump_json(),
            )
            verdict, _ = llm.generate_structured(prompt, EvalJudgeVerdict)
            passed, score = verdict.score >= 4, verdict.score
        except ValueError:
            continue
        except Exception:
            passed, score = False, 1
        conn.execute(
            "INSERT INTO eval_results (run_at, case_id, passed, score) VALUES (?,?,?,?)",
            (run_at, case.case_id, int(passed), score),
        )
        results.append({"case_id": case.case_id, "passed": passed, "score": score})
    conn.commit()
    return results
