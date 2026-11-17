import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pipeline.models import FailureCategory


class EvalCase(BaseModel):
    case_id: str
    trace_id: str
    failing_step: str
    category: FailureCategory
    original_input: dict[str, Any]
    bad_output: dict[str, Any]
    corrected_output: dict[str, Any]


def create_case(
    conn: sqlite3.Connection, evals_dir: Path, case: EvalCase, created_at: str
) -> None:
    evals_dir.mkdir(parents=True, exist_ok=True)
    path = evals_dir / f"{case.case_id}.json"
    path.write_text(case.model_dump_json(indent=2), encoding="utf-8")
    conn.execute(
        "INSERT OR REPLACE INTO eval_cases "
        "(case_id, trace_id, failing_step, category, created_at, json_path) "
        "VALUES (?,?,?,?,?,?)",
        (case.case_id, case.trace_id, case.failing_step,
         case.category.value, created_at, str(path)),
    )
    conn.commit()


def list_cases(conn: sqlite3.Connection, evals_dir: Path) -> list[EvalCase]:
    rows = conn.execute("SELECT json_path FROM eval_cases ORDER BY created_at").fetchall()
    return [EvalCase.model_validate_json(Path(r["json_path"]).read_text(encoding="utf-8"))
            for r in rows]
